# 更新记录 / Changelog

每个版本改了什么。安装包在 GitHub 的 Releases 里下载。
What changed in each version. The installer is on the GitHub Releases page.

## 未发布 / Unreleased

- **支持 macOS**（11 及以上，Apple 芯片和 Intel）：`RedCrab.app` 装在 .dmg 里（`RedCrab-<版本>-macOS-arm64.dmg` / `-x86_64.dmg`），由 `installer/build_mac.py` 打包。桌宠、动作、养成、图鉴、四家的 hook 和所有 `clawd` 命令都和 Windows 上一样；托盘图标在菜单栏，开机自启是登录时打开。装法和不同之处见 README 的“在 macOS 上安装和使用”。
  **macOS support** (11 or later, Apple silicon and Intel): `RedCrab.app` in a .dmg (`RedCrab-<version>-macOS-arm64.dmg` / `-x86_64.dmg`), built by `installer/build_mac.py`. The pets, actions, growth, the album, the hooks for the four agents and every `clawd` command are as on Windows; the tray icon is in the menu bar, and Start with Windows is Open at Login. How to install it and what differs: "Installing and using on macOS" in the README.
  - `clawd_mac/` 在 Mac 上用 AppKit 接住桌宠的 Win32 调用，用 Quartz 代替 GDI+，见 `clawd_mac/README.md`。
    `clawd_mac/` serves the pets' Win32 calls over AppKit on a Mac, and GDI+ over Quartz; see `clawd_mac/README.md`.
  - GitHub Actions：`macOS` 工作流在每次 push 和 pull request 时跑测试并打一个 arm64 的 .dmg；手动的 `Build` 在 Setup.exe 旁边也打 arm64 和 Intel 的 .dmg。
    GitHub Actions: the `macOS` workflow runs the tests and builds an arm64 .dmg on every push and pull request; the manual `Build` also makes arm64 and Intel .dmg files next to Setup.exe.

## 1.0.0（2026-11-16）

第一个公开版本。发布前最后的调整：
The first public version. Last changes before the release:

- **翻找和经验按“干活时间”算，不再按回合数**：长回合和短回合拿到的一样多，新手前期也能稳定翻到东西。
  **Digging and XP go by work time, not by the number of turns**: long and short turns earn alike, and the first hours bring finds steadily.
  - 干活时间：AI 真在干活的时间。等你批准或回复（橙色圆圈）不算，5 分钟没动静不算（命令还在跑照算）。几个对话同时干活：小的自己翻和经验各算各的，亲手翻的机会只算一份。
    Work time: the time the AI really works. Waiting for your approval or answer (an orange circle) does not count, nor 5 minutes without a word (unless a command still runs). Several conversations at once: digs by themselves and XP count for each, digs by hand count the time once.
  - 亲手翻的机会：每干活 10 分钟马上给 1 次，回合中途也给，零头留着（最多存 3/4/5 次）。
    Digs by hand: one each 10 minutes of work, given at once, in the middle of a turn too; what is over is kept (3/4/5 kept at most).
  - 它自己翻：一个回合每干 2 分钟活，小的翻一次，四成能翻到；一个回合最多 3/4/5 次（和能存的机会一样）。
    By itself: each 2 minutes of a turn's work a small one digs, four in ten finding something; at most 3/4/5 a turn (as many as the chances kept).
  - 回合经验：5 点 + 每分钟干活 2 点，不再封顶（原来一个回合最多 25 点）。
    A turn's XP: 5 plus 2 per minute of work, no cap any more (it was 25 at most).
- **卸载和升级更干净**：先关掉开着的图鉴和“连接 AI”窗口（原来它们占着文件，卸载会留下一些文件）；卸载时把各家设置旁边的那一个备份也删掉。
  **Cleaner uninstall and update**: the album and Connect AI windows are closed first (they held files, so an uninstall left some behind); uninstalling also removes the one backup kept beside each agent's settings.
- 图鉴里“翻找机会”的说明改对了。
  The album's line about digs left now says how they are earned.
