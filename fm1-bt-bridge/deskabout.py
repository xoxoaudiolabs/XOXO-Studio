"""MORE > STUDIO SETTINGS > ABOUT: the Studio's version, and three QR codes to scan with a phone: the Studio's code on GitHub, the
XOXO Audio Labs website, and this Studio's web app (its address on the network now: the phone on the same Wi-Fi).
Mixed into deskui.DeskUI. The codes are made by python3-qrcode (Raspberry Pi OS's package); without it, the
addresses are written out instead."""

import socket
import time

import deskboot
import xoxostyle as st

W, H, HDR_H, TAB_H = 480, 320, 34, 44
REPO = "https://github.com/xoxoaudiolabs/XOXO-Studio"
SITE = "https://xoxoaudiolabs.com"
WEB_PORT = 80                                   # web.py's
QR_SIZE = 124                                   # each code's square, its quiet zone in it


def lan_address():
    """this Studio's address on the network (the one a phone on the same Wi-Fi reaches it at), or None. Nothing is
    sent: connecting a UDP socket only picks the way out."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))             # (a documentation address: never reached)
        ip = s.getsockname()[0]
        return None if ip.startswith(("127.", "0.")) else ip
    except OSError:
        return None
    finally:
        s.close()


def web_url(ip):
    return f"http://{ip}/" if WEB_PORT == 80 else f"http://{ip}:{WEB_PORT}/"


def qr_modules(text):
    """the QR code's modules for text, [[bool]] with a quiet zone of two, or None without python3-qrcode"""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    return q.get_matrix()


class DeskAbout:
    def about_init(self):
        self.about_ip, self.about_ip_at = None, -1e9

    def about_view(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.about_ip_at > 5:          # the address, looked at again every 5 s (Wi-Fi can come and go)
            self.about_ip, self.about_ip_at = lan_address(), now
        return (self.about_ip,)

    def draw_about(self, img, d, now):
        t = self.theme
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< BACK", lambda: self.open_tab("SETTINGS"), key="about-back")
        st.text(img, (96, 9), "ABOUT", t.hi)
        version = f"XOXO STUDIO {deskboot.VERSION}"
        st.text(img, (W - 10 - st.text_size(version)[0], 9), version, t.c[3])
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        ip = self.about_view(time.monotonic())[0]
        codes = [("THE CODE", REPO, "github.com"), ("XOXO AUDIO LABS", SITE, "xoxoaudiolabs.com"),
                 ("WEB APP", ip and web_url(ip), ip or "no network")]
        cw = W // 3
        for k, (title, url, under) in enumerate(codes):
            x0 = k * cw
            self.centre(img, (x0, HDR_H + 4, x0 + cw, HDR_H + 22), title, t.track[k])
            box = (x0 + (cw - QR_SIZE) // 2, HDR_H + 26, x0 + (cw + QR_SIZE) // 2, HDR_H + 26 + QR_SIZE)
            self.draw_qr(img, d, box, url)
            self.centre(img, (x0, box[3] + 4, x0 + cw, box[3] + 22), under, t.c[3])
        note = "Scan WEB APP with a phone on the same Wi-Fi as the Studio" if ip else "Join Wi-Fi (MORE > WI-FI) for the web app"
        self.centre(img, (0, H - TAB_H - 26, W, H - TAB_H - 8), note, t.c[2])

    def draw_qr(self, img, d, box, url):
        """url's QR code in box, dark on white (as phones read them best); none: the box empty"""
        t = self.theme
        modules = qr_modules(url) if url else None
        if not modules:
            d.rectangle(box, outline=t.c[1])
            if url:                             # (no python3-qrcode: the address itself)
                self.centre(img, box, "NO QR", t.c[2])
            return
        n = len(modules)
        scale = (box[2] - box[0]) // n
        size = scale * n
        x0, y0 = box[0] + (box[2] - box[0] - size) // 2, box[1] + (box[3] - box[1] - size) // 2
        d.rectangle((x0, y0, x0 + size - 1, y0 + size - 1), fill=(255, 255, 255))
        for r, row in enumerate(modules):
            for c, dark in enumerate(row):
                if dark:
                    d.rectangle((x0 + c * scale, y0 + r * scale, x0 + (c + 1) * scale - 1,
                                 y0 + (r + 1) * scale - 1), fill=(0, 0, 0))
