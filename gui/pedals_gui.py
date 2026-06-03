#!/usr/bin/env python3
# =====================================================================
#  SIM Pedals - GUI completa (Tkinter + pyserial)
#  Protocolo casado com sim_pedals.ino v1.0.0
#  Novidades v3.8:
#    - bscale (escala do freio) com slider + presets
#    - envio de curva em thread (não trava a UI)
#    - parse do novo campo CFG (bscale)
#    - botão diag (P2P de ruído do freio)
# =====================================================================
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading, queue, time, json, os
from collections import deque

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    raise SystemExit("Instale pyserial:  pip install pyserial")

BAUD = 115200
HID_MAX = 1023
LUT_N = 32

CFG_KEYS = [
    ("axMin", 0, 4095, 1),
    ("axMax", 0, 4095, 1),
    ("ayMin", 0, 4095, 1),
    ("ayMax", 0, 4095, 1),
    ("bMin",  0, 16000000, 1000),
    ("bMax",  0, 16000000, 1000),
    ("dz",    0, 200, 1),
    ("ga",    0.2, 4.0, 0.1),
    ("ema",   1, 1000, 10),
    ("bscale", -10.0, 10.0, 0.1),   # NOVO
]
CFG_ORDER = ["axMin","axMax","ayMin","ayMax","bMin","bMax",
             "dz","invx","invy","invb","ga","ema","useCurve",
             "btnen","invbtn","bscale"]   # bscale no fim

BG, GRID, CURVE_C, LIVE_C = "#0d1117", "#21262d", "#c792ea", "#3fa7ff"
SAT_C, OK_C = "#e74c3c", "#27ae60"
SC_X, SC_Y, SC_B = "#ff5f5f", "#3fa7ff", "#ffd166"   # cores dos eixos no osc.


# =====================================================================
#  Editor de curva LUT (canvas com pontos arrastáveis)
# =====================================================================
class CurveEditor(tk.Canvas):
    def __init__(self, parent, on_change=None, n_handles=9, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, **kw)
        self.on_change = on_change
        self.n = n_handles
        self.hx = [i / (self.n - 1) for i in range(self.n)]
        self.hy = [i / (self.n - 1) for i in range(self.n)]
        self.drag = None
        self.live = 0.0
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)

    def _px(self, nx, ny, w, h, pad):
        return pad + nx * (w - 2 * pad), pad + (1 - ny) * (h - 2 * pad)

    def _nearest(self, mx, my, w, h, pad):
        best, bd = None, 1e9
        for i in range(self.n):
            px, py = self._px(self.hx[i], self.hy[i], w, h, pad)
            d = (px - mx) ** 2 + (py - my) ** 2
            if d < bd:
                bd, best = d, i
        return best if bd < 400 else None

    def _press(self, e):
        self.drag = self._nearest(e.x, e.y, self.winfo_width(),
                                  self.winfo_height(), 28)

    def _move(self, e):
        if self.drag is None:
            return
        h = self.winfo_height(); pad = 28
        ny = 1 - (e.y - pad) / (h - 2 * pad)
        self.hy[self.drag] = max(0.0, min(1.0, ny))
        self.redraw()

    def _release(self, e):
        if self.drag is not None:
            self.drag = None
            if self.on_change:
                self.on_change(self.get_lut())

    def _interp(self, x):
        for i in range(self.n - 1):
            if self.hx[i] <= x <= self.hx[i + 1]:
                t = (x - self.hx[i]) / (self.hx[i + 1] - self.hx[i] + 1e-9)
                t = t * t * (3 - 2 * t)
                return self.hy[i] + (self.hy[i + 1] - self.hy[i]) * t
        return self.hy[-1]

    def get_lut(self):
        return [int(round(max(0.0, min(1.0, self._interp(k / (LUT_N - 1)))) * HID_MAX))
                for k in range(LUT_N)]

    def set_lut(self, lut):
        for i in range(self.n):
            k = self.hx[i] * (LUT_N - 1)
            k0 = int(k); k1 = min(k0 + 1, LUT_N - 1); fr = k - k0
            v = lut[k0] + (lut[k1] - lut[k0]) * fr
            self.hy[i] = max(0.0, min(1.0, v / HID_MAX))
        self.redraw()

    def set_preset(self, kind):
        for i in range(self.n):
            x = self.hx[i]
            if   kind == "linear": y = x
            elif kind == "suave":  y = x ** 1.6
            elif kind == "forte":  y = x ** 0.6
            elif kind == "s":      y = x * x * (3 - 2 * x)
            else:                  y = x
            self.hy[i] = y
        self.redraw()
        if self.on_change:
            self.on_change(self.get_lut())

    def set_live(self, n_in):
        self.live = max(0.0, min(1.0, n_in))

    def redraw(self):
        self.delete("all")
        w = self.winfo_width() or 500
        h = self.winfo_height() or 260
        pad = 28
        for f in (0, .25, .5, .75, 1):
            x = pad + f * (w - 2 * pad); y = pad + (1 - f) * (h - 2 * pad)
            self.create_line(x, pad, x, h - pad, fill=GRID)
            self.create_line(pad, y, w - pad, y, fill=GRID)
        self.create_text(pad - 4, h - pad + 12, text="0", fill="#586069",
                         font=("Consolas", 7))
        self.create_text(w - pad, h - pad + 12, text="força 100%", fill="#586069",
                         anchor="e", font=("Consolas", 7))
        self.create_text(pad - 4, pad - 6, text="saída 100%", fill="#586069",
                         anchor="w", font=("Consolas", 7))
        pts = []
        for s in range(81):
            x = s / 80; y = self._interp(x)
            px, py = self._px(x, y, w, h, pad); pts.extend((px, py))
        if len(pts) >= 4:
            self.create_line(*pts, fill=CURVE_C, width=2, smooth=True)
        if self.live > 0:
            lx, _ = self._px(self.live, 0, w, h, pad)
            self.create_line(lx, pad, lx, h - pad, fill=LIVE_C, dash=(3, 2))
            ly = self._interp(self.live)
            mx, my = self._px(self.live, ly, w, h, pad)
            self.create_oval(mx - 4, my - 4, mx + 4, my + 4, fill=LIVE_C, outline="")
        for i in range(self.n):
            px, py = self._px(self.hx[i], self.hy[i], w, h, pad)
            self.create_oval(px - 6, py - 6, px + 6, py + 6,
                             fill="#ff5f5f", outline="#fff", width=1)


# =====================================================================
#  Osciloscópio (histórico rolante dos 3 eixos)
# =====================================================================
class Scope(tk.Canvas):
    def __init__(self, parent, maxlen=300, **kw):
        super().__init__(parent, bg="#08090d", highlightthickness=0, **kw)
        self.maxlen = maxlen
        self.bufx = deque(maxlen=maxlen)
        self.bufy = deque(maxlen=maxlen)
        self.bufb = deque(maxlen=maxlen)
        self.show = {"x": True, "y": True, "b": True}
        self.paused = False
        self.bind("<Configure>", lambda e: self.redraw())

    def set_window(self, n):
        n = int(n)
        self.maxlen = n
        self.bufx = deque(self.bufx, maxlen=n)
        self.bufy = deque(self.bufy, maxlen=n)
        self.bufb = deque(self.bufb, maxlen=n)

    def push(self, x, y, b):
        if self.paused:
            return
        self.bufx.append(x); self.bufy.append(y); self.bufb.append(b)

    def clear(self):
        self.bufx.clear(); self.bufy.clear(); self.bufb.clear()
        self.redraw()

    def _series(self, buf, w, h, pad):
        n = len(buf)
        if n < 2:
            return []
        pts = []
        step = (w - 2 * pad) / (self.maxlen - 1)
        x0 = pad + (self.maxlen - n) * step
        for i, v in enumerate(buf):
            px = x0 + i * step
            py = pad + (1 - v / HID_MAX) * (h - 2 * pad)
            pts.extend((px, py))
        return pts

    def redraw(self):
        self.delete("all")
        w = self.winfo_width() or 600
        h = self.winfo_height() or 280
        pad = 26
        for f in (0, .25, .5, .75, 1):
            y = pad + (1 - f) * (h - 2 * pad)
            self.create_line(pad, y, w - pad, y, fill=GRID)
            self.create_text(pad - 4, y, text=str(int(f * HID_MAX)),
                             fill="#586069", anchor="e", font=("Consolas", 7))
        for f in (0, .25, .5, .75, 1):
            x = pad + f * (w - 2 * pad)
            self.create_line(x, pad, x, h - pad, fill=GRID)
        if self.show["x"]:
            p = self._series(self.bufx, w, h, pad)
            if p: self.create_line(*p, fill=SC_X, width=2)
        if self.show["y"]:
            p = self._series(self.bufy, w, h, pad)
            if p: self.create_line(*p, fill=SC_Y, width=2)
        if self.show["b"]:
            p = self._series(self.bufb, w, h, pad)
            if p: self.create_line(*p, fill=SC_B, width=2)
        lg = [("X acel", SC_X, self.bufx), ("Y embr", SC_Y, self.bufy),
              ("Xrot freio", SC_B, self.bufb)]
        x = pad + 6
        for name, c, buf in lg:
            cur = buf[-1] if buf else 0
            t = f"{name}: {cur}"
            self.create_rectangle(x, pad + 2, x + 10, pad + 12, fill=c, outline="")
            self.create_text(x + 14, pad + 7, text=t, fill=c,
                             anchor="w", font=("Consolas", 8))
            x += 14 + len(t) * 6 + 18
        if self.paused:
            self.create_text(w - pad, pad + 7, text="⏸ PAUSADO",
                             fill="#f1c40f", anchor="e", font=("Consolas", 9, "bold"))


# =====================================================================
#  Aplicação
# =====================================================================
class PedalsGUI:
    def __init__(self, root):
        self.root = root
        root.title("SIM Pedals - Config v1.0.0 - DrEaD SimGear")
        root.geometry("960x860")
        root.configure(bg=BG)

        self.ser = None
        self.running = False
        self.q = queue.Queue()
        self.monitor_on = False
        self.calibrating = None
        self.live = {"rawAx": 0, "rawAy": 0, "rawB": 0,
                     "hx": 0, "hy": 0, "hb": 0, "btn": 0}

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_main  = ttk.Frame(nb)
        self.tab_curve = ttk.Frame(nb)
        self.tab_scope = ttk.Frame(nb)
        self.tab_prof  = ttk.Frame(nb)
        nb.add(self.tab_main,  text="  Monitor / Calibração  ")
        nb.add(self.tab_curve, text="  Curva do Freio  ")
        nb.add(self.tab_scope, text="  Osciloscópio  ")
        nb.add(self.tab_prof,  text="  Perfis  ")

        self._build_conn(self.tab_main)
        self._build_cfg(self.tab_main)
        self._build_inv(self.tab_main)
        self._build_bscale(self.tab_main)     # NOVO
        self._build_button(self.tab_main)
        self._build_brake(self.tab_main)
        self._build_autocal(self.tab_main)
        self._build_bars(self.tab_main)
        self._build_log(self.tab_main)
        self._build_curve_tab(self.tab_curve)
        self._build_scope_tab(self.tab_scope)
        self._build_profiles_tab(self.tab_prof)

        self._refresh_ports()
        self.root.after(50, self._pump)
        self.root.after(60, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ============================ CONEXÃO ============================
    def _build_conn(self, parent):
        f = ttk.LabelFrame(parent, text="Conexão")
        f.pack(fill="x", padx=8, pady=4)
        self.cb_port = ttk.Combobox(f, width=30, state="readonly")
        self.cb_port.pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="↻", width=3, command=self._refresh_ports).pack(side="left")
        self.btn_conn = ttk.Button(f, text="Conectar", command=self._toggle_conn)
        self.btn_conn.pack(side="left", padx=4)
        self.btn_mon = ttk.Button(f, text="Monitor OFF", command=self._toggle_monitor,
                                  state="disabled")
        self.btn_mon.pack(side="left", padx=4)
        self.lbl_state = ttk.Label(f, text="● desconectado", foreground="red")
        self.lbl_state.pack(side="left", padx=8)

    def _refresh_ports(self):
        self._port_map = {}
        labels = []
        for p in serial.tools.list_ports.comports():
            label = p.device
            desc = (p.description or "") + (p.manufacturer or "")
            if any(t in desc.lower() for t in ("maple", "stm", "1eaf", "composite")):
                label += "  ★"
            self._port_map[label] = p.device
            labels.append(label)
        self.cb_port["values"] = labels
        if labels and not self.cb_port.get():
            star = next((l for l in labels if "★" in l), labels[0])
            self.cb_port.set(star)

    def _selected_port(self):
        return self._port_map.get(self.cb_port.get(), self.cb_port.get())

    # ============================ CONFIG ============================
    def _build_cfg(self, parent):
        f = ttk.LabelFrame(parent, text="Configuração")
        f.pack(fill="x", padx=8, pady=4)
        self.vars = {}
        row = ttk.Frame(f); row.pack(fill="x")
        for i, (key, lo, hi, step) in enumerate(CFG_KEYS):
            if i and i % 5 == 0:
                row = ttk.Frame(f); row.pack(fill="x")
            self._spin(row, key, lo, lo, hi, step)
        bar = ttk.Frame(f); bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Ler CFG (?)", command=lambda: self.send("?")).pack(side="left", padx=3)
        ttk.Button(bar, text="Enviar todos", command=self._send_all_cfg).pack(side="left", padx=3)
        ttk.Button(bar, text="Salvar EEPROM", command=lambda: self.send("save")).pack(side="left", padx=3)
        ttk.Button(bar, text="Recarregar", command=lambda: self.send("load")).pack(side="left", padx=3)
        ttk.Button(bar, text="Defaults", command=self._do_defaults).pack(side="left", padx=3)
        ttk.Button(bar, text="Diag ruído", command=lambda: self.send("diag")).pack(side="left", padx=3)

    def _spin(self, parent, key, default, lo, hi, step):
        box = ttk.Frame(parent); box.pack(side="left", padx=3)
        ttk.Label(box, text=key).pack()
        var = tk.StringVar(value=str(default))
        ttk.Spinbox(box, from_=lo, to=hi, increment=step,
                    textvariable=var, width=8).pack()
        ttk.Button(box, text="Set", width=5,
                   command=lambda k=key, v=var: self.send(f"{k} {v.get()}")).pack()
        self.vars[key] = var

    def _send_all_cfg(self):
        def worker():
            for key in self.vars:
                self.send(f"{key} {self.vars[key].get()}"); time.sleep(0.02)
            for key in self.inv:
                self.send(f"{key} {self.inv[key].get()}"); time.sleep(0.02)
            self.send(f"btnen {self.var_btnen.get()}"); time.sleep(0.02)
            self.send(f"invbtn {self.var_invbtn.get()}"); time.sleep(0.02)
        threading.Thread(target=worker, daemon=True).start()

    def _do_defaults(self):
        if messagebox.askyesno("Defaults", "Restaurar configurações padrão na placa?"):
            self.send("def")

    # ============================ INVERSÕES ============================
    def _build_inv(self, parent):
        f = ttk.LabelFrame(parent, text="Inversões de eixo")
        f.pack(fill="x", padx=8, pady=4)
        self.inv = {}
        for key in ("invx", "invy", "invb"):
            v = tk.IntVar(value=0)
            self.inv[key] = v
            ttk.Checkbutton(f, text=key, variable=v,
                            command=lambda k=key, vv=v: self.send(f"{k} {vv.get()}")
                            ).pack(side="left", padx=8)

    # ===================== BSCALE (escala do freio) =====================
    def _build_bscale(self, parent):
        f = ttk.LabelFrame(parent, text="Escala do freio (bscale) — sensibilidade/sentido")
        f.pack(fill="x", padx=8, pady=4)
        self.var_bscale = tk.DoubleVar(value=1.0)
        ttk.Label(f, text="−3").pack(side="left", padx=2)
        self.scl_bscale = ttk.Scale(f, from_=-3.0, to=3.0, variable=self.var_bscale,
                                    length=300, command=self._bscale_drag)
        self.scl_bscale.pack(side="left", padx=4)
        ttk.Label(f, text="+3").pack(side="left", padx=2)
        self.lbl_bscale = ttk.Label(f, text="1.00", width=6, foreground="#ffd166")
        self.lbl_bscale.pack(side="left", padx=6)
        for txt, val in (("0", 0.0), ("+1", 1.0), ("−1", -1.0)):
            ttk.Button(f, text=txt, width=4,
                       command=lambda v=val: self._bscale_preset(v)).pack(side="left", padx=2)
        ttk.Label(f, text="(>1 mais sensível · <1 menos · negativo inverte)",
                  foreground="#888").pack(side="left", padx=8)

    def _bscale_drag(self, _e=None):
        v = round(self.var_bscale.get(), 2)
        self.lbl_bscale.config(text=f"{v:.2f}")
        # também atualiza o spin em CFG_KEYS, se existir
        if "bscale" in self.vars:
            self.vars["bscale"].set(f"{v:.2f}")
        self.send(f"bscale {v}")

    def _bscale_preset(self, v):
        self.var_bscale.set(v)
        self._bscale_drag()

    # ======================= BOTÃO FÍSICO HID =======================
    def _build_button(self, parent):
        f = ttk.LabelFrame(parent, text="Botão físico HID (PB5 · INPUT_PULLUP)")
        f.pack(fill="x", padx=8, pady=4)
        self.var_btnen = tk.IntVar(value=1)
        self.var_invbtn = tk.IntVar(value=0)
        ttk.Checkbutton(f, text="Habilitar botão (btnen)", variable=self.var_btnen,
                        command=lambda: self.send(f"btnen {self.var_btnen.get()}")
                        ).pack(side="left", padx=8)
        ttk.Checkbutton(f, text="Inverter (invbtn)", variable=self.var_invbtn,
                        command=lambda: self.send(f"invbtn {self.var_invbtn.get()}")
                        ).pack(side="left", padx=8)
        self.led_btn = tk.Canvas(f, width=22, height=22, bg=BG, highlightthickness=0)
        self.led_btn.pack(side="left", padx=8)
        self._btn_led = self.led_btn.create_oval(4, 4, 18, 18, fill="#333", outline="#555")
        ttk.Label(f, text="estado ao vivo →", foreground="#888").pack(side="left")

    # ===================== TARA / FULL DO FREIO =====================
    def _build_brake(self, parent):
        f = ttk.LabelFrame(parent, text="Calibração rápida do freio (load cell)")
        f.pack(fill="x", padx=8, pady=4)
        self.btn_bzero = ttk.Button(f, text="⊘ Tara/Zero (bMin)",
                                    command=lambda: self._brake_cmd("bzero"),
                                    state="disabled")
        self.btn_bzero.pack(side="left", padx=6, pady=4)
        self.btn_bfull = ttk.Button(f, text="⛂ Pisar fundo (bMax)",
                                    command=lambda: self._brake_cmd("bfull"),
                                    state="disabled")
        self.btn_bfull.pack(side="left", padx=6)
        ttk.Label(f, text="(solte p/ zero · pise no máx p/ full)",
                  foreground="#888").pack(side="left", padx=8)

    def _brake_cmd(self, cmd):
        if cmd == "bfull" and not messagebox.askyesno(
                "Pisar fundo", "Mantenha o pedal de freio no máximo e confirme."):
            return
        self.send(cmd)

    # ===================== AUTO-CALIBRAÇÃO =====================
    def _build_autocal(self, parent):
        f = ttk.LabelFrame(parent, text="Auto-calibração de eixos (mova no fim de curso)")
        f.pack(fill="x", padx=8, pady=4)
        self.btn_cal = ttk.Button(f, text="▶ Iniciar auto-cal",
                                  command=self._toggle_autocal, state="disabled")
        self.btn_cal.pack(side="left", padx=6, pady=4)
        self.lbl_cal = ttk.Label(f, text="parado", foreground="#888")
        self.lbl_cal.pack(side="left", padx=8)

    def _toggle_autocal(self):
        if self.calibrating:
            self._finish_autocal()
        else:
            self._start_autocal()

    def _start_autocal(self):
        if not self.monitor_on:
            self._toggle_monitor()
        self.calibrating = {"axMin": 99999, "axMax": -99999,
                            "ayMin": 99999, "ayMax": -99999,
                            "bMin": 99999999, "bMax": -99999999}
        self.btn_cal.config(text="■ Parar e aplicar")
        self.lbl_cal.config(text="capturando... mova TODOS os pedais",
                            foreground="#f1c40f")

    def _accumulate_cal(self):
        c = self.calibrating
        if not c:
            return
        c["axMin"] = min(c["axMin"], self.live["rawAx"])
        c["axMax"] = max(c["axMax"], self.live["rawAx"])
        c["ayMin"] = min(c["ayMin"], self.live["rawAy"])
        c["ayMax"] = max(c["ayMax"], self.live["rawAy"])
        c["bMin"]  = min(c["bMin"],  self.live["rawB"])
        c["bMax"]  = max(c["bMax"],  self.live["rawB"])
        self.lbl_cal.config(
            text=f"ax[{c['axMin']}..{c['axMax']}] "
                 f"ay[{c['ayMin']}..{c['ayMax']}] b[{c['bMin']}..{c['bMax']}]")

    def _finish_autocal(self):
        c = self.calibrating
        self.calibrating = None
        self.btn_cal.config(text="▶ Iniciar auto-cal")
        if not c or c["axMax"] <= c["axMin"]:
            self.lbl_cal.config(text="cancelado (sem dados)", foreground="#888")
            return

        def marg(lo, hi, pct=0.02):
            d = int((hi - lo) * pct)
            return lo + d, hi - d

        axMin, axMax = marg(c["axMin"], c["axMax"])
        ayMin, ayMax = marg(c["ayMin"], c["ayMax"])
        sets = {"axMin": axMin, "axMax": axMax, "ayMin": ayMin, "ayMax": ayMax,
                "bMin": c["bMin"], "bMax": c["bMax"]}

        def worker():
            for k, v in sets.items():
                self.send(f"{k} {v}")
                self.vars[k].set(str(v))
                time.sleep(0.02)
            self.lbl_cal.config(text="aplicado! (use 'Salvar EEPROM')", foreground=OK_C)
        threading.Thread(target=worker, daemon=True).start()

    # ============================ BARRAS ============================
    def _build_bars(self, parent):
        f = ttk.LabelFrame(parent, text="Telemetria (HID 0..1023)")
        f.pack(fill="x", padx=8, pady=4)
        self.bars, self.bvals = {}, {}
        for name in ("X (acel)", "Y (embr)", "Xrot (freio)"):
            row = ttk.Frame(f); row.pack(fill="x", padx=6, pady=2)
            ttk.Label(row, text=name, width=12).pack(side="left")
            pb = ttk.Progressbar(row, maximum=HID_MAX, length=440)
            pb.pack(side="left", padx=6)
            lbl = ttk.Label(row, text="0", width=6); lbl.pack(side="left")
            sat = ttk.Label(row, text="  ", width=6); sat.pack(side="left")
            self.bars[name] = pb; self.bvals[name] = (lbl, sat)
        self.lbl_raw = ttk.Label(f, text="RAW: ax=- ay=- b=-  ·  BTN: -",
                                 foreground="#888")
        self.lbl_raw.pack(anchor="w", padx=8, pady=2)

    # ============================ LOG ============================
    def _build_log(self, parent):
        f = ttk.LabelFrame(parent, text="Log serial")
        f.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt = tk.Text(f, height=5, bg="#111", fg="#0f0",
                           insertbackground="#0f0", font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(f, command=self.txt.yview); sb.pack(side="right", fill="y")
        self.txt.config(yscrollcommand=sb.set)

    def _log(self, msg):
        self.txt.insert("end", msg + "\n"); self.txt.see("end")
        if int(self.txt.index("end-1c").split(".")[0]) > 500:
            self.txt.delete("1.0", "100.0")

    # ============================ ABA CURVA ============================
    def _build_curve_tab(self, parent):
        top = ttk.LabelFrame(parent, text="Curva do Freio — arraste os pontos")
        top.pack(fill="both", expand=True, padx=8, pady=6)
        self.curve = CurveEditor(top, on_change=self._on_curve_change,
                                 n_handles=9, height=340)
        self.curve.pack(fill="both", expand=True, padx=6, pady=6)

        bar = ttk.Frame(parent); bar.pack(fill="x", padx=8, pady=4)
        for t, k in [("Linear", "linear"), ("Progressiva", "suave"),
                     ("Agressiva", "forte"), ("S-curve", "s")]:
            ttk.Button(bar, text=t,
                       command=lambda k=k: self.curve.set_preset(k)).pack(side="left", padx=3)

        ctl = ttk.Frame(parent); ctl.pack(fill="x", padx=8, pady=6)
        self.var_usecurve = tk.IntVar(value=0)
        ttk.Checkbutton(ctl, text="Ativar curva no firmware (usecurve)",
                        variable=self.var_usecurve,
                        command=self._toggle_usecurve).pack(side="left", padx=4)
        ttk.Button(ctl, text="Enviar curva",
                   command=lambda: self._send_curve(self.curve.get_lut())).pack(side="left", padx=8)
        ttk.Button(ctl, text="Ler curva (getcurve)",
                   command=lambda: self.send("getcurve")).pack(side="left", padx=4)
        ttk.Button(ctl, text="Salvar EEPROM",
                   command=lambda: self.send("save")).pack(side="left", padx=8)
        ttk.Label(parent, foreground="#888",
                  text="Dica: linha azul = força atual do freio (Monitor ON).").pack(
            fill="x", padx=10, pady=4)
        # debounce do envio da curva
        self._curve_pending = None
        self._curve_send_lock = threading.Lock()

    def _on_curve_change(self, lut):
        # debounce: agenda envio em thread, não trava UI
        if self.ser and self.ser.is_open:
            self._curve_pending = list(lut)
            threading.Thread(target=self._debounced_curve, daemon=True).start()

    def _debounced_curve(self):
        time.sleep(0.15)
        with self._curve_send_lock:
            lut = self._curve_pending
            if lut is None:
                return
            self._curve_pending = None
        self._send_curve(lut)

    def _toggle_usecurve(self):
        self.send(f"usecurve {self.var_usecurve.get()}")

    def _send_curve(self, lut):
        def worker():
            for i in range(0, LUT_N, 8):
                self.send("curve %d %s" % (i, " ".join(str(v) for v in lut[i:i + 8])))
                time.sleep(0.02)
        threading.Thread(target=worker, daemon=True).start()

    # ============================ ABA OSCILOSCÓPIO ============================
    def _build_scope_tab(self, parent):
        ctl = ttk.Frame(parent); ctl.pack(fill="x", padx=8, pady=6)
        self.sc_x = tk.IntVar(value=1); self.sc_y = tk.IntVar(value=1)
        self.sc_b = tk.IntVar(value=1)
        ttk.Checkbutton(ctl, text="X acel", variable=self.sc_x,
                        command=self._scope_toggle).pack(side="left", padx=6)
        ttk.Checkbutton(ctl, text="Y embr", variable=self.sc_y,
                        command=self._scope_toggle).pack(side="left", padx=6)
        ttk.Checkbutton(ctl, text="Xrot freio", variable=self.sc_b,
                        command=self._scope_toggle).pack(side="left", padx=6)

        ttk.Label(ctl, text="   janela:").pack(side="left")
        self.sc_win = tk.IntVar(value=300)
        ttk.Scale(ctl, from_=100, to=1000, variable=self.sc_win, length=160,
                  command=lambda e: self.scope.set_window(self.sc_win.get())
                  ).pack(side="left", padx=4)
        self.lbl_win = ttk.Label(ctl, text="300 am.", foreground="#888")
        self.lbl_win.pack(side="left")

        self.btn_pause = ttk.Button(ctl, text="⏸ Pausar", command=self._scope_pause)
        self.btn_pause.pack(side="left", padx=10)
        ttk.Button(ctl, text="🗑 Limpar",
                   command=lambda: self.scope.clear()).pack(side="left", padx=4)

        self.scope = Scope(parent, maxlen=300, height=420)
        self.scope.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(parent, foreground="#888",
                  text="Histórico em tempo real (50 Hz com Monitor ON). "
                       "Cada amostra = 1 pacote DATA.").pack(fill="x", padx=10, pady=4)

    def _scope_toggle(self):
        self.scope.show = {"x": bool(self.sc_x.get()),
                           "y": bool(self.sc_y.get()),
                           "b": bool(self.sc_b.get())}

    def _scope_pause(self):
        self.scope.paused = not self.scope.paused
        self.btn_pause.config(text="▶ Retomar" if self.scope.paused else "⏸ Pausar")

    # ============================ ABA PERFIS ============================
    def _build_profiles_tab(self, parent):
        f = ttk.LabelFrame(parent, text="Perfis de configuração (.json)")
        f.pack(fill="x", padx=8, pady=8)
        ttk.Button(f, text="💾 Salvar perfil...", command=self._save_profile).pack(side="left", padx=6, pady=8)
        ttk.Button(f, text="📂 Carregar perfil...", command=self._load_profile).pack(side="left", padx=6)
        ttk.Button(f, text="⬆ Enviar p/ placa", command=self._apply_loaded_profile).pack(side="left", padx=6)

        info = ttk.LabelFrame(parent, text="Perfil atual (em memória)")
        info.pack(fill="both", expand=True, padx=8, pady=6)
        self.txt_prof = tk.Text(info, height=16, bg="#0b0b0b", fg="#9cd",
                                font=("Consolas", 9))
        self.txt_prof.pack(fill="both", expand=True, padx=6, pady=6)
        self.loaded_profile = None
        ttk.Label(parent, foreground="#888",
                  text="Inclui CFG, inversões, gamma, bscale, usecurve, LUT(32) e botão.").pack(
            fill="x", padx=10, pady=4)

    def _current_profile_dict(self):
        prof = {"version": "1.0.0", "cfg": {}, "inv": {}, "lut": self.curve.get_lut()}
        for key in self.vars:
            prof["cfg"][key] = self.vars[key].get()
        for key in self.inv:
            prof["inv"][key] = self.inv[key].get()
        prof["usecurve"] = self.var_usecurve.get()
        prof["btnen"] = self.var_btnen.get()
        prof["invbtn"] = self.var_invbtn.get()
        prof["bscale"] = round(self.var_bscale.get(), 3)
        return prof

    def _show_profile(self, prof):
        self.txt_prof.delete("1.0", "end")
        self.txt_prof.insert("end", json.dumps(prof, indent=2, ensure_ascii=False))

    def _save_profile(self):
        prof = self._current_profile_dict()
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Perfil JSON", "*.json")],
            initialfile="meu_perfil.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(prof, fp, indent=2, ensure_ascii=False)
            self._show_profile(prof)
            self._log(f"[perfil salvo] {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _load_profile(self):
        path = filedialog.askopenfilename(filetypes=[("Perfil JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                prof = json.load(fp)
            self.loaded_profile = prof
            self._show_profile(prof)
            for key, v in prof.get("cfg", {}).items():
                if key in self.vars:
                    self.vars[key].set(str(v))
            for key, v in prof.get("inv", {}).items():
                if key in self.inv:
                    self.inv[key].set(int(v))
            self.var_usecurve.set(int(prof.get("usecurve", 0)))
            self.var_btnen.set(int(prof.get("btnen", 1)))
            self.var_invbtn.set(int(prof.get("invbtn", 0)))
            bs = float(prof.get("bscale", 1.0))
            self.var_bscale.set(bs); self.lbl_bscale.config(text=f"{bs:.2f}")
            if "lut" in prof and len(prof["lut"]) >= LUT_N:
                self.curve.set_lut(prof["lut"][:LUT_N])
            self._log(f"[perfil carregado] {os.path.basename(path)} (clique 'Enviar p/ placa')")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _apply_loaded_profile(self):
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Conexão", "Conecte a placa primeiro.")
            return
        self._send_all_cfg()
        self.send(f"bscale {round(self.var_bscale.get(), 3)}")
        self.send(f"usecurve {self.var_usecurve.get()}")
        self._send_curve(self.curve.get_lut())
        self._log("[perfil enviado] revise e clique 'Salvar EEPROM' p/ persistir")

    # ============================ SERIAL ============================
    def _toggle_conn(self):
        if self.ser and self.ser.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self._selected_port()
        if not port:
            messagebox.showwarning("Porta", "Selecione uma porta serial."); return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir {port}:\n{e}"); return
        self.running = True
        threading.Thread(target=self._read_loop, daemon=True).start()
        self.btn_conn.config(text="Desconectar")
        for b in (self.btn_mon, self.btn_cal, self.btn_bzero, self.btn_bfull):
            b.config(state="normal")
        self.lbl_state.config(text="● conectado", foreground="green")
        self._log(f"[conectado] {port} @ {BAUD}")
        time.sleep(0.3)
        self.send("?"); self.send("getcurve")

    def _disconnect(self):
        self.running = False
        if self.monitor_on:
            self.send("l"); self.monitor_on = False
        time.sleep(0.1)
        try:
            if self.ser: self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.calibrating = None
        self.btn_conn.config(text="Conectar")
        self.btn_mon.config(text="Monitor OFF", state="disabled")
        self.btn_cal.config(text="▶ Iniciar auto-cal", state="disabled")
        for b in (self.btn_bzero, self.btn_bfull):
            b.config(state="disabled")
        self.lbl_state.config(text="● desconectado", foreground="red")
        self._log("[desconectado]")

    def send(self, cmd):
        if not (self.ser and self.ser.is_open):
            self._log(f"[ignorado] {cmd} (sem conexão)"); return
        try:
            self.ser.write((cmd + "\n").encode()); self._log(f">> {cmd}")
        except Exception as e:
            self._log(f"[erro envio] {e}")

    def _toggle_monitor(self):
        self.send("l")
        self.monitor_on = not self.monitor_on
        self.btn_mon.config(text="Monitor ON" if self.monitor_on else "Monitor OFF")

    def _read_loop(self):
        buf = b""
        while self.running and self.ser and self.ser.is_open:
            try:
                buf += self.ser.read(256)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    s = line.decode(errors="replace").strip()
                    if s:
                        self.q.put(s)
            except Exception:
                break

    # ============================ LOOPS UI ============================
    def _pump(self):
        try:
            while True:
                self._handle_line(self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(40, self._pump)

    def _tick(self):
        self.curve.set_live(self.live["hb"] / HID_MAX)
        self.curve.redraw()
        self.scope.redraw()
        self.lbl_win.config(text=f"{self.sc_win.get()} am.")
        on = bool(self.live.get("btn"))
        self.led_btn.itemconfig(self._btn_led,
                                fill=("#2ecc71" if on else "#333"),
                                outline=("#27ae60" if on else "#555"))
        if self.calibrating:
            self._accumulate_cal()
        self.root.after(60, self._tick)

    def _handle_line(self, line):
        if line.startswith("DATA,"):
            self._update_bars(line)
        elif line.startswith("CFG,"):
            self._update_cfg(line); self._log(line)
        elif line.startswith("CURVE"):
            self._update_curve(line)
        else:
            self._log(line)
            if "SIM Pedals OK" in line:
                self._log("[placa detectada ✔]")

    def _update_bars(self, line):
        try:
            p = line.split(",")
            rawAx, rawAy, rawB = int(p[1]), int(p[2]), int(p[3])
            hx, hy, hb = int(p[4]), int(p[5]), int(p[6])
            btn = int(p[7]) if len(p) > 7 else 0
        except (IndexError, ValueError):
            return
        self.live.update(rawAx=rawAx, rawAy=rawAy, rawB=rawB,
                         hx=hx, hy=hy, hb=hb, btn=btn)
        self.scope.push(hx, hy, hb)
        vals = {"X (acel)": hx, "Y (embr)": hy, "Xrot (freio)": hb}
        for name, v in vals.items():
            self.bars[name]["value"] = v
            lbl, sat = self.bvals[name]
            lbl.config(text=str(v))
            if v >= HID_MAX:
                sat.config(text="SAT▲", foreground=SAT_C)
            elif v <= 0:
                sat.config(text="ZERO", foreground=SAT_C)
            else:
                sat.config(text="  ", foreground="#888")
        self.lbl_raw.config(
            text=f"RAW: ax={rawAx} ay={rawAy} b={rawB}  ·  BTN: {'ON' if btn else 'off'}")

    def _update_cfg(self, line):
        p = line.split(",")[1:]
        data = dict(zip(CFG_ORDER, p))
        for key in self.vars:
            if key in data:
                self.vars[key].set(data[key])
        for key in self.inv:
            if key in data:
                self.inv[key].set(1 if data[key] not in ("0", "0.0") else 0)
        if "useCurve" in data:
            self.var_usecurve.set(1 if data["useCurve"] not in ("0", "0.0") else 0)
        if "btnen" in data:
            self.var_btnen.set(1 if data["btnen"] not in ("0", "0.0") else 0)
        if "invbtn" in data:
            self.var_invbtn.set(1 if data["invbtn"] not in ("0", "0.0") else 0)
        if "bscale" in data:
            try:
                bs = float(data["bscale"])
                self.var_bscale.set(bs); self.lbl_bscale.config(text=f"{bs:.2f}")
            except ValueError:
                pass

    def _update_curve(self, line):
        try:
            vals = [int(x) for x in line.split(",")[1:]]
            if len(vals) >= LUT_N:
                self.curve.set_lut(vals[:LUT_N])
                self._log(">> curva carregada do firmware")
        except ValueError:
            pass

    def _on_close(self):
        try:
            self._disconnect()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    PedalsGUI(root)
    root.mainloop()
