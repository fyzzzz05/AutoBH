import Cocoa
import WebKit
import Sparkle

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, SPUUpdaterDelegate, NSMenuItemValidation, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var engine: Process?
    var parentPipe: Pipe?
    var outputPipe: Pipe?
    var handshake = Data()
    var serverURL: URL?
    var quitting = false
    var startupFailed = false
    var updaterController: SPUStandardUpdaterController?
    var updateRequested = false
    var preparingUpdate = false
    var workersPrepared = false
    var recoveryTimer: Timer?
    var recoveryRunning = false
    var isDemo: Bool { CommandLine.arguments.contains("--demo") || ProcessInfo.processInfo.environment["AUTOBH_DESKTOP_DEMO"] == "1" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        if let iconURL = Bundle.main.url(forResource: "AutoBH", withExtension: "icns"),
           let icon = NSImage(contentsOf: iconURL) {
            NSApp.applicationIconImage = icon
        }
        applyAppearance(isDemo ? "system" : UserDefaults.standard.string(forKey: "AutoBH.Appearance") ?? "system")
        buildMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "AutoBH"
        window.minSize = NSSize(width: 560, height: 600)
        window.center()
        window.setFrameAutosaveName("AutoBH.MainWindow")
        let label = NSTextField(labelWithString: "正在打开 AutoBH…")
        label.font = .systemFont(ofSize: 18)
        label.alignment = .center
        label.translatesAutoresizingMaskIntoConstraints = false
        let loading = NSView()
        loading.addSubview(label)
        NSLayoutConstraint.activate([label.centerXAnchor.constraint(equalTo: loading.centerXAnchor), label.centerYAnchor.constraint(equalTo: loading.centerYAnchor)])
        window.contentView = loading
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        launchEngine()
        if !isDemo {
            updaterController = SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: self, userDriverDelegate: nil)
            recoverWorkers(action: "rollback")
            recoveryTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.recoverWorkers() }
        }
    }

    func buildMenu() {
        let main = NSMenu()
        let application = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于 AutoBH", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        let update = NSMenuItem(title: "检查更新…", action: #selector(checkForUpdates), keyEquivalent: "")
        update.target = self
        appMenu.addItem(update)
        let automatic = NSMenuItem(title: "自动检查更新", action: #selector(toggleAutomaticUpdates), keyEquivalent: "")
        automatic.target = self
        appMenu.addItem(automatic)
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 AutoBH", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 AutoBH", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        application.submenu = appMenu
        main.addItem(application)
        let edit = NSMenuItem()
        let editMenu = NSMenu(title: "编辑")
        for (title, selector, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        edit.submenu = editMenu
        main.addItem(edit)
        let view = NSMenuItem()
        let viewMenu = NSMenu(title: "视图")
        let reload = NSMenuItem(title: "刷新页面", action: #selector(reloadPage), keyEquivalent: "r")
        reload.target = self
        viewMenu.addItem(reload)
        view.submenu = viewMenu
        main.addItem(view)
        NSApp.mainMenu = main
    }

    @objc func reloadPage() { webView?.reload() }

    @objc func checkForUpdates() { updaterController?.checkForUpdates(nil) }
    @objc func toggleAutomaticUpdates() {
        guard let updater = updaterController?.updater else { return }
        updater.automaticallyChecksForUpdates.toggle()
    }
    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        if menuItem.action == #selector(checkForUpdates) {
            return updaterController?.updater.canCheckForUpdates == true && !preparingUpdate
        }
        if menuItem.action == #selector(toggleAutomaticUpdates) {
            menuItem.state = updaterController?.updater.automaticallyChecksForUpdates == true ? .on : .off
            return updaterController != nil
        }
        return true
    }

    func workerHandoff(_ action: String, completion: @escaping (Bool, String) -> Void) {
        guard let resource = Bundle.main.resourceURL else { completion(false, "安装包资源缺失"); return }
        let executable = resource.appendingPathComponent("engine/autobh-engine")
        let environment = ProcessInfo.processInfo.environment.filter { !["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"].contains($0.key) }
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            process.executableURL = executable
            process.arguments = ["--update-workers", action]
            process.environment = environment.merging(["PYINSTALLER_RESET_ENVIRONMENT": "1"]) { _, new in new }
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = FileHandle.nullDevice
            let errors = Pipe()
            process.standardError = errors
            do {
                try process.run()
                let detail = errors.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let message = String(data: detail, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                DispatchQueue.main.async { completion(process.terminationStatus == 0, message) }
            } catch {
                DispatchQueue.main.async { completion(false, "无法保存后台状态，请稍后重试") }
            }
        }
    }

    func recoverWorkers(action: String = "resume") {
        guard !isDemo, !recoveryRunning, !preparingUpdate, !quitting else { return }
        recoveryRunning = true
        workerHandoff(action) { [weak self] _, _ in self?.recoveryRunning = false }
    }

    func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) { updateRequested = true }
    func updaterWillRelaunchApplication(_ updater: SPUUpdater) { updateRequested = true }
    func updater(_ updater: SPUUpdater, willInstallUpdateOnQuit item: SUAppcastItem, immediateInstallationBlock: @escaping () -> Void) -> Bool {
        updateRequested = true
        return false
    }
    func updater(_ updater: SPUUpdater, didAbortWithError error: Error) {
        updateRequested = false
        workersPrepared = false
        recoverWorkers(action: "rollback")
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard updateRequested, !isDemo else { return .terminateNow }
        if workersPrepared { return .terminateNow }
        if preparingUpdate { return .terminateLater }
        preparingUpdate = true
        window.title = "AutoBH · 正在保存后台进度…"
        workerHandoff("prepare") { [weak self] success, message in
            guard let self = self else { return }
            self.preparingUpdate = false
            self.workersPrepared = success
            if !success { self.updateRequested = false }
            NSApp.reply(toApplicationShouldTerminate: success)
            if !success {
                self.window.title = "AutoBH"
                let alert = NSAlert()
                alert.messageText = "更新已暂缓"
                alert.informativeText = message.isEmpty ? "后台仍在处理当前操作，请稍后重试。" : message
                alert.addButton(withTitle: "好")
                alert.beginSheetModal(for: self.window)
            }
        }
        return .terminateLater
    }


    func launchEngine() {
        guard let resource = Bundle.main.resourceURL else { fail("安装包缺少资源目录。"); return }
        let executable = resource.appendingPathComponent("engine/autobh-engine")
        let child = Process()
        child.executableURL = executable
        var args = ["--desktop-server", "--watch-parent"]
        if CommandLine.arguments.contains("--demo") || ProcessInfo.processInfo.environment["AUTOBH_DESKTOP_DEMO"] == "1" { args.append("--demo") }
        child.arguments = args
        var environment = ProcessInfo.processInfo.environment
        for key in ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"] { environment.removeValue(forKey: key) }
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        child.environment = environment
        let input = Pipe()
        let output = Pipe()
        child.standardInput = input
        child.standardOutput = output
        let logDirectory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/AutoBH")
        do {
            try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
            let log = logDirectory.appendingPathComponent("desktop.log")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600]) }
            let logHandle = try FileHandle(forWritingTo: log)
            logHandle.seekToEndOfFile()
            child.standardError = logHandle
        } catch { child.standardError = FileHandle.nullDevice }
        parentPipe = input
        outputPipe = output
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.receive(data) }
        }
        child.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, !self.quitting, !self.startupFailed else { return }
                self.fail("管理服务已退出。请重新打开 AutoBH。\n运行记录：~/Library/Logs/AutoBH/desktop.log")
            }
        }
        engine = child
        do { try child.run() } catch { fail(error.localizedDescription) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self = self, self.serverURL == nil, !self.quitting, !self.startupFailed else { return }
            self.fail("管理服务启动超时。请重新打开 AutoBH。")
        }
    }

    func receive(_ data: Data) {
        guard serverURL == nil, !startupFailed else { return }
        handshake.append(data)
        guard let newline = handshake.firstIndex(of: 10) else {
            if handshake.count > 8192 { fail("管理服务返回的数据无效。") }
            return
        }
        guard let object = try? JSONSerialization.jsonObject(with: handshake.prefix(upTo: newline)) as? [String: String],
              let value = object["url"], let url = URL(string: value), url.scheme == "http", url.host == "127.0.0.1", url.port != nil else {
            fail("无法连接本机管理服务。")
            return
        }
        serverURL = url
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(self, name: "appearance")
        applyAppearance(object["appearance"] ?? "system")
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = false
        window.contentView = webView
        webView.load(URLRequest(url: url))
    }

    private func applyAppearance(_ mode: String) {
        guard ["system", "light", "dark"].contains(mode) else { return }
        NSApp.appearance = mode == "system" ? nil : NSAppearance(named: mode == "dark" ? .darkAqua : .aqua)
        if !isDemo { UserDefaults.standard.set(mode, forKey: "AutoBH.Appearance") }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "appearance", message.webView === webView, message.frameInfo.isMainFrame,
              let origin = serverURL, let url = message.frameInfo.request.url,
              url.scheme == origin.scheme, url.host == origin.host, url.port == origin.port,
              let mode = message.body as? String else { return }
        applyAppearance(mode)
    }

    func fail(_ message: String) {
        guard !startupFailed, !quitting else { return }
        startupFailed = true
        let alert = NSAlert()
        alert.messageText = "AutoBH 无法打开"
        alert.informativeText = message
        alert.addButton(withTitle: "退出")
        alert.runModal()
        NSApp.terminate(nil)
    }

    private func isSchoolLoginURL(_ url: URL) -> Bool {
        url.scheme == "https" && ["sso.buaa.edu.cn", "app.buaa.edu.cn", "ygdk.buaa.edu.cn"].contains(url.host ?? "") && url.user == nil && url.password == nil && (url.port == nil || url.port == 443)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if webView === self.webView, action.navigationType == .linkActivated,
           let url = action.request.url, isSchoolLoginURL(url) {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let server = serverURL else { decisionHandler(.cancel); return }
        if webView === self.webView, action.navigationType == .linkActivated, isSchoolLoginURL(url) {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(url.scheme == server.scheme && url.host == server.host && url.port == server.port ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { window.makeKeyAndOrderFront(nil); return true }
    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        recoveryTimer?.invalidate()
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        try? parentPipe?.fileHandleForWriting.close()
        if engine?.isRunning == true { engine?.terminate() }
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.run()
