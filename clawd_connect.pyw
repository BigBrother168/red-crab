# -*- coding: utf-8 -*-
"""Clawd: the window that connects the AI agents (连接 AI): connect and disconnect, then Apply.  The pets open it at
their very first start; after that 连接 AI… in the right-click and the tray menu, and clawd connect.  A process of its
own (tkinter), like the album.

    pythonw clawd_connect.pyw [--home DIR] [--selftest OUT.json [--check a,b] [--uncheck a,b]]

One row per agent clawd.py knows (AGENT_ORDER): its name with a tick, what it is now (connected, not connected, its
paths to update, not found on this computer, its settings unreadable: the last two greyed) and, when the tick says
otherwise, what Apply will do (connect, disconnect, update).  The ticks start as things are; with none connected yet
(the first start) every agent found is ticked.  Apply is grey until a tick changes something; it connects or
disconnects each through clawd.py's set_hooks / cmd_hooks (only our own entries, the file backed up first), says
under each row how it went and what is left to do (NEXT_STEP: trust the hooks in Codex, restart DeepSeek ...), and
the window stays for more.  Close (or Esc) closes it.
--home   the pets' home (its state.json gives the language); default: as clawd.py finds it.
--selftest  shows itself, ticks --check and unticks --uncheck, presses Apply, writes what each row says and each
         agent's state after into OUT.json, and closes (tests run it with the agents' folders elsewhere).
"""
import ctypes
import importlib.machinery
import importlib.util
import json
import os
import sys
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
BG = "#FAF7F2"
INK = "#2B2B2B"
SOFT = "#6E6A64"
OK_C = "#2E7D4F"
WARN_C = "#B5652B"
BAD_C = "#B03A2E"
ACCENT = "#C4572F"


def load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


class Connect(object):
    def __init__(self, cl, selftest=None, check=(), uncheck=()):
        self.cl = cl
        self.T = T = cl.T
        self.selftest, self.check, self.uncheck = selftest, set(check), set(uncheck)
        self.root = root = tk.Tk()
        root.withdraw()
        root.title(T("Clawd · 连接 AI", "Clawd · Connect AI"))
        root.configure(bg=BG)
        root.resizable(False, False)
        self.f = root.winfo_fpixels("1i") / 96.0
        zh = cl.get_lang() == "zh"
        face = "Microsoft YaHei UI" if zh else "Segoe UI"
        self.font = (face, -self.S(14))
        self.small = (face, -self.S(12))
        self.head = (face, -self.S(18), "bold")
        self.bold = (face, -self.S(14), "bold")
        st = ttk.Style(root)
        st.configure("C.TCheckbutton", background=BG, foreground=INK, font=self.bold)
        st.configure("C.TButton", font=self.font, padding=(self.S(14), self.S(5)))
        self.pictures()
        pad = self.S(22)
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=pad, pady=(pad, self.S(6)))
        if self.crab is not None:
            tk.Label(top, image=self.crab, bg=BG).pack(side="left", padx=(0, self.S(14)))
        words = tk.Frame(top, bg=BG)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text=T("让一家三口跟着你的 AI 干活", "Let the family follow your AI at work"),
                 font=self.head, fg=INK, bg=BG, anchor="w").pack(fill="x")
        tk.Label(words, text=T("勾上就连接，取消勾选就断开，点“应用”生效。\n只改 Clawd 自己加的几行，改之前先备份。",
                               "Tick to connect, untick to disconnect, then Apply. Only Clawd's own lines are "
                               "changed, backed up first."),
                 font=self.small, fg=SOFT, bg=BG, anchor="w", justify="left",     # (Tk breaks Chinese only at spaces)
                 wraplength=0 if zh else self.S(380)).pack(fill="x", pady=(self.S(4), 0))
        box = tk.Frame(root, bg=BG)
        box.pack(fill="x", padx=pad, pady=self.S(8))
        box.columnconfigure(2, weight=1)           # the words under a row take room from the last column
        self.rows = {}
        found = {a: cl.agent_found(a) for a in cl.AGENT_ORDER}
        states = {a: cl.hook_state(a) for a in cl.AGENT_ORDER}
        first = not any(s in ("on", "old") for s in states.values())
        found_any = False
        for i, agent in enumerate(cl.AGENT_ORDER):
            state = states[agent]
            usable = state != "bad" and (found[agent] or state in ("on", "old"))
            found_any = found_any or usable
            tick = usable and (state in ("on", "old") or first)
            tick = (tick or agent in self.check) and agent not in self.uncheck and usable
            var = tk.BooleanVar(value=tick)
            cb = ttk.Checkbutton(box, text=cl.AGENTS[agent]["name"], variable=var, style="C.TCheckbutton",
                                 state="normal" if usable else "disabled", command=self.changed)
            cb.grid(row=2 * i, column=0, sticky="w", pady=(self.S(6), 0))
            note = tk.Label(box, font=self.font, bg=BG, anchor="w")
            note.grid(row=2 * i, column=1, sticky="w", padx=(self.S(16), 0), pady=(self.S(6), 0))
            todo = tk.Label(box, font=self.font, fg=ACCENT, bg=BG, anchor="w")
            todo.grid(row=2 * i, column=2, sticky="w", padx=(self.S(10), 0), pady=(self.S(6), 0))
            more = tk.Label(box, font=self.small, fg=SOFT, bg=BG, anchor="w", justify="left", wraplength=self.S(400))
            more.grid(row=2 * i + 1, column=0, columnspan=3, sticky="w", padx=(self.S(26), 0))
            self.rows[agent] = {"var": var, "cb": cb, "note": note, "todo": todo, "more": more, "state": state,
                                "found": found[agent], "usable": usable, "result": None}
        if not found_any:
            tk.Label(root, text=T("这台电脑上还没找到这四家 AI。装好、用过一次以后，再从菜单里的“连接 AI…”来连。",
                                  "None of these four AI agents has run on this computer yet. Once one has, connect "
                                  "it from Connect AI… in the menu."),
                     font=self.small, fg=WARN_C, bg=BG, justify="left", wraplength=self.S(440)).pack(fill="x", padx=pad)
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=pad, pady=(self.S(12), pad))
        self.apply_btn = ttk.Button(bar, text=T("应用", "Apply"), style="C.TButton", command=self.apply)
        self.close_btn = ttk.Button(bar, text=T("关闭", "Close"), style="C.TButton", command=root.destroy)
        if found_any:
            self.apply_btn.pack(side="right")
        self.close_btn.pack(side="right", padx=(0, self.S(10)) if found_any else 0)
        self.changed()
        import tkinter.font as tkfont               # the window keeps its width: the "will ..." column keeps room for
        f = tkfont.Font(root, font=self.font)       # the longest, the words under the rows wrap inside the rows' width
        box.columnconfigure(2, minsize=max(f.measure(T(*w)) for w in (("→ 将断开", "→ will disconnect"),
                                                                       ("→ 将连接", "→ will connect"))) + self.S(10))
        root.update_idletasks()
        self.zh, self.small_f, self.wrap_w = zh, tkfont.Font(root, font=self.small), box.winfo_reqwidth() - self.S(26)
        for r in self.rows.values():
            r["more"].configure(wraplength=0 if zh else self.wrap_w)
        root.bind("<Escape>", lambda e: root.destroy())
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.geometry("+%d+%d" % ((root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 3))
        root.deiconify()
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
        root.focus_force()
        if selftest:
            root.after(600, self.run_selftest)

    def S(self, px):
        return max(1, int(round(px * self.f)))

    def pictures(self):
        """The window's icon and the crab waving at the top, from the frames (300 % if there)."""
        self.crab, self.icons = None, []
        try:
            al = load("clawd_album", "clawd_album.pyw")
            hi = os.path.join(HERE, "frames_hi")
            fr = al.Frames(hi if os.path.isfile(os.path.join(hi, "manifest.json")) else os.path.join(HERE, "frames"))
            for clip, side, keep in (("wave", self.S(76), True), ("idle", 48, False), ("idle", 32, False), ("idle", 16, False)):
                got = fr.frame(clip, None if clip == "wave" else 0)
                if got is None:
                    continue
                raw, box, _ = got
                s = (box[2] - box[0]) / (side * 0.95)
                img = tk.PhotoImage(data=al.png(al.layer(raw, fr.W, fr.H, box, fr.anchor, s, 0, 0), side, side), format="png")
                if keep:
                    self.crab = img
                else:
                    self.icons.append(img)
            if self.icons:
                self.root.iconphoto(True, *self.icons)
        except Exception:
            pass

    def lines(self, text):
        """Chinese broken into lines that fit under a row (Tk breaks only at spaces, Chinese has few): between Chinese
        characters, a Latin word (/hooks) kept whole, a mark like ，。） never at the start of a line (the character
        before it goes down with it).  English: Tk's own wrapping."""
        if not self.zh:
            return text
        import re
        marks = "，。、；：！？）》”"
        out, line = [], []
        for tok in re.findall(r"[!-~]+|\s|.", text):
            if line and self.small_f.measure("".join(line) + tok) > self.wrap_w:
                carry = []
                if tok in marks:                       # down with it: the marks before it and one character
                    while len(line) > 1 and (not carry or carry[0] in marks):
                        carry.insert(0, line.pop())
                out.append("".join(line).rstrip())
                line = carry
                if tok.isspace():
                    continue
            line.append(tok)
        return "\n".join(out + ["".join(line)])

    def pending(self, r):
        """What Apply will do to this row: "connect", "update", "disconnect" or None."""
        if not r["usable"]:
            return None
        want, state = r["var"].get(), r["state"]
        if want:
            return {"off": "connect", "old": "update"}.get(state)
        return "disconnect" if state in ("on", "old") else None

    def changed(self):
        """Each row: what it is now and, if the tick says otherwise, what Apply will do; Apply grey with nothing to do."""
        T, n = self.T, 0
        for r in self.rows.values():
            state = r["state"]
            if state == "bad":
                text, colour = T("设置文件读不了，没动它", "Its settings cannot be read; left alone"), BAD_C
            elif state == "on":
                text, colour = T("已连接", "Connected"), OK_C
            elif state == "old":
                text, colour = T("已连接，路径要更新", "Connected, paths to update"), WARN_C
            elif r["found"]:
                text, colour = T("未连接", "Not connected"), INK
            else:
                text, colour = T("这台电脑上没找到", "Not found on this computer"), SOFT
            r["note"].configure(text=text, fg=colour)
            p = self.pending(r)
            n += p is not None
            r["todo"].configure(text={"connect": T("→ 将连接", "→ will connect"), "update": T("→ 将更新", "→ will update"),
                                      "disconnect": T("→ 将断开", "→ will disconnect")}.get(p, ""))
        self.apply_btn.state(["!disabled"] if n else ["disabled"])

    def apply(self):
        cl, T = self.cl, self.T
        for agent, r in self.rows.items():
            p = self.pending(r)
            if p is None:
                continue
            ok, text = cl.set_hooks(agent, p != "disconnect")
            r["state"] = cl.hook_state(agent)
            r["result"] = {"did": p, "ok": ok, "text": text}
            if not ok:
                lines = [l for l in text.splitlines() if l.strip() and not l.startswith(("已备份", "Backed up"))]
                r["more"].configure(text=self.lines(T("✗ 没改成：", "✗ Not changed: ") + " ".join(lines)[:200]), fg=BAD_C)
            elif p == "disconnect":
                r["more"].configure(text=self.lines(T("✓ 已断开，它干活时一家不再跟着动。",
                                                      "✓ Disconnected: the family no longer follows it.")), fg=SOFT)
            else:
                r["more"].configure(text=self.lines("✓ " + T(*cl.NEXT_STEP[agent])), fg=SOFT)
        self.changed()

    def run_selftest(self):
        out = {}
        try:
            out["before"] = {a: r["todo"].cget("text") for a, r in self.rows.items()}
            out["apply_grey_before"] = self.apply_btn.instate(["disabled"])
            self.apply()
            self.root.update()
            for agent, r in self.rows.items():
                out[agent] = {"found": r["found"], "usable": r["usable"], "state": r["state"],
                              "note": r["note"].cget("text"), "todo": r["todo"].cget("text"),
                              "more": r["more"].cget("text"), "result": r["result"]}
            out["window"] = [self.root.winfo_width(), self.root.winfo_height()]
            out["apply_grey"] = self.apply_btn.instate(["disabled"])
        except Exception as e:
            out["error"] = repr(e)
        with open(self.selftest, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        self.root.after(1500 if os.environ.get("CLAWD_SELFTEST_LINGER") else 0, self.root.destroy)


def main(argv):
    home = selftest = None
    check = uncheck = ()
    i = 1
    while i < len(argv):
        if argv[i] == "--home" and i + 1 < len(argv):
            home = os.path.abspath(argv[i + 1]); i += 1
        elif argv[i] == "--selftest" and i + 1 < len(argv):
            selftest = os.path.abspath(argv[i + 1]); i += 1
        elif argv[i] == "--check" and i + 1 < len(argv):
            check = tuple(a for a in argv[i + 1].split(",") if a); i += 1
        elif argv[i] == "--uncheck" and i + 1 < len(argv):
            uncheck = tuple(a for a in argv[i + 1].split(",") if a); i += 1
        i += 1
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW(None, False, "Local\\ClawdConnect")
    if k32.GetLastError() == 183 and not selftest:     # one at a time: the open one comes to the front
        u32 = ctypes.windll.user32
        for title in ("Clawd · 连接 AI", "Clawd · Connect AI"):
            hwnd = u32.FindWindowW(None, title)
            if hwnd:
                u32.ShowWindow(hwnd, 9)
                u32.SetForegroundWindow(hwnd)
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    cl = load("clawd", "clawd.py")
    if home:
        cl.HOME, cl.STATE_FILE = home, os.path.join(home, "state.json")
    Connect(cl, selftest, check, uncheck).root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
