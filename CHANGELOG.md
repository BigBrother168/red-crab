# 更新记录 / Changelog

每个版本改了什么。安装包在 GitHub 的 Releases 里下载。
What changed in each version. The installer is on the GitHub Releases page.

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
