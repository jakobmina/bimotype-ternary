import flet as ft
import time
import os
import json
import sys
import io
import base64
import threading

# Add parent directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from bimotype_ternary.network.p2p import MetriplecticPeer
from bimotype_ternary.network.discovery import PeerDiscovery
from bimotype_ternary.crypto.qr_transfer import QRTransferProtocol


def main(page: ft.Page):
    page.title = "BiMoType Metriplectic Console"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 400
    page.window_height = 800
    page.vertical_alignment = ft.MainAxisAlignment.START

    # ── Theme Constants ────────────────────────────────────────────────────────
    BG_COLOR      = "#0b0e14"
    ACCENT_COLOR  = "#00d4ff"
    SURFACE_COLOR = "#161b22"
    GLASS_COLOR   = "#1f293780" # semi-transparent
    SHADOW_COLOR  = "#000000a0"

    page.bgcolor = BG_COLOR

    state = {
        "peer": None,
        "local_fp": None,
        "messages": [],
        "handshake_requests": [],
        "target_fp": "",
        "h7_seed": 42,
        "qr_frames_b64": [],
        "animating": False,
        "symplectic_energy": 0.5,
        "metric_entropy": 0.5
    }

    # ── Peer init ─────────────────────────────────────────────────────────────

    def on_peer_message(sender, packet):
        if state["peer"]:
            decoded = state["peer"].decoder.decode_bimotype_packet(packet)
            msg_text = decoded.get("decoded_message", "Error al decodificar")
            state["messages"].append({
                "role": "assistant",
                "sender": sender[:8],
                "content": msg_text
            })
            page.run_task(lambda: update_chat_ui())

    def on_handshake(sender):
        if sender not in state["handshake_requests"]:
            state["handshake_requests"].append(sender)
            page.run_task(lambda: update_handshake_ui())

    def init_peer_async():
        import random
        port = random.randint(5100, 5200)
        state["peer"] = MetriplecticPeer(port=port)
        state["peer"].on_message_received = on_peer_message
        state["peer"].on_handshake_received = on_handshake
        state["peer"].on_trust_established = lambda _: page.run_task(lambda: update_contacts_ui())
        state["local_fp"] = state["peer"].start_listening(thread_callback=lambda t=None: None)
        PeerDiscovery.register_peer(state["local_fp"], "127.0.0.1", port)
        page.run_task(lambda: update_ui_on_init())

    threading.Thread(target=init_peer_async, daemon=True).start()

    # ── UI Components ─────────────────────────────────────────────────────────

    chat_list = ft.ListView(expand=True, spacing=12, auto_scroll=True, padding=10)

    msg_input = ft.TextField(
        hint_text="Mensaje encriptado...",
        expand=True,
        border_radius=20,
        border_color=ACCENT_COLOR,
        color=ft.Colors.WHITE,
        bgcolor=SURFACE_COLOR,
        content_padding=ft.Padding(15, 10, 15, 10)
    )

    target_fp_input = ft.TextField(
        label="Objetivo (Fingerprint)",
        hint_text="e.g. 0x8a2b...",
        border_color=ACCENT_COLOR,
        color=ACCENT_COLOR,
        bgcolor=SURFACE_COLOR,
        border_radius=10,
        text_size=12
    )

    handshake_column = ft.Column(spacing=8)
    contacts_column = ft.Column(spacing=8)

    identity_text = ft.Text("Inicializando...", font_family="monospace", size=11, color=ACCENT_COLOR)
    
    # Metriplectic Monitor (Rule 3.3)
    symplectic_bar = ft.ProgressBar(value=0.5, color=ACCENT_COLOR, bgcolor=ft.Colors.BLUE_GREY_900)
    metric_bar = ft.ProgressBar(value=0.5, color=ft.Colors.PURPLE_400, bgcolor=ft.Colors.BLUE_GREY_900)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def snack(text, color=ft.Colors.BLUE_700):
        page.snack_bar = ft.SnackBar(ft.Text(text, weight=ft.FontWeight.BOLD), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def update_ui_on_init():
        identity_text.value = state["local_fp"]
        update_contacts_ui()
        update_metriplectic_monitor()
        page.update()

    def update_metriplectic_monitor():
        import random
        # simulated dynamics for visual feedback
        state["symplectic_energy"] = max(0.1, min(0.9, state["symplectic_energy"] + random.uniform(-0.05, 0.05)))
        state["metric_entropy"] = 1.0 - state["symplectic_energy"]
        symplectic_bar.value = state["symplectic_energy"]
        metric_bar.value = state["metric_entropy"]
        page.update()

    def update_contacts_ui():
        contacts_column.controls.clear()
        trusted = state["peer"].trusted_peers
        if not trusted:
            contacts_column.controls.append(
                ft.Text("Sin contactos de confianza", size=12, italic=True, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
            )
        else:
            for t_fp in list(trusted):
                def set_target(e, fp=t_fp):
                    target_fp_input.value = fp
                    page.update()
                    snack(f"Target set to: {fp[:8]}...", ft.Colors.BLUE_700)

                contacts_column.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK_PERSON, color=ACCENT_COLOR, size=20),
                            ft.Text(f"{t_fp[:12]}...", color=ft.Colors.WHITE, expand=True, weight=ft.FontWeight.W_500),
                            ft.IconButton(ft.Icons.CHAT_BUBBLE_ROUNDED, on_click=set_target, icon_color=ACCENT_COLOR)
                        ]),
                        bgcolor=SURFACE_COLOR,
                        padding=10,
                        border_radius=12,
                        on_click=set_target
                    )
                )

        # Discovery section
        discovered_controls = []
        peers = PeerDiscovery.get_all_peers()
        for fp, data in peers.items():
            if fp != state["local_fp"] and fp not in trusted:
                def request_hs(e, target_fp=fp, host=data["host"], port=data["port"]):
                    state["peer"].request_handshake(host, port)
                    snack(f"Handshake request sent to {target_fp[:8]}", ft.Colors.ORANGE_800)

                discovered_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.WIFI_TETHERING, color=ft.Colors.GREY_400, size=18),
                            ft.Text(f"{fp[:8]}...", color=ft.Colors.GREY_400, expand=True),
                            ft.TextButton("Handshake", on_click=request_hs, font_family="monospace", style=ft.ButtonStyle(color=ft.Colors.ORANGE_400))
                        ]),
                        bgcolor=ft.Colors.TRANSPARENT,
                        padding=5
                    )
                )

        if discovered_controls:
            contacts_column.controls.append(
                ft.ExpansionTile(
                    title=ft.Text("Discovery Node", size=13, color=ft.Colors.GREY_400, weight=ft.FontWeight.BOLD),
                    controls=discovered_controls,
                    icon_color=ft.Colors.GREY_400,
                )
            )
        page.update()

    def update_handshake_ui():
        handshake_column.controls.clear()
        for req_fp in state["handshake_requests"]:
            target_data = PeerDiscovery.resolve_peer(req_fp)

            def acc_click(e, fp=req_fp, t_data=target_data):
                if t_data:
                    state["peer"].send_handshake_ack(t_data[0], t_data[1], fp)
                state["handshake_requests"].remove(fp)
                snack(f"Trust established with {fp[:8]}", ft.Colors.GREEN_700)
                update_handshake_ui()
                update_contacts_ui()

            def ign_click(e, fp=req_fp):
                state["handshake_requests"].remove(fp)
                update_handshake_ui()

            handshake_column.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SECURITY, color=ft.Colors.ORANGE_400),
                        ft.Text(f"REQ: {req_fp[:8]}...", weight=ft.FontWeight.BOLD),
                        ft.Row([
                            ft.IconButton(ft.Icons.CHECK_CIRCLE, on_click=acc_click, icon_color=ft.Colors.GREEN_400),
                            ft.IconButton(ft.Icons.CANCEL, on_click=ign_click, icon_color=ft.Colors.RED_400),
                        ], spacing=0)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor=ft.Colors.with_opacity(0.2, ft.Colors.ORANGE_900),
                    padding=10,
                    border_radius=10,
                    border=ft.Border.all(1, ft.Colors.ORANGE_800)
                )
            )
        page.update()

    def update_chat_ui():
        chat_list.controls.clear()
        for msg in state["messages"]:
            is_user = msg["role"] == "user"
            align  = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
            color  = ACCENT_COLOR if is_user else ft.Colors.WHITE
            bg     = ft.Colors.with_opacity(0.15, ACCENT_COLOR) if is_user else SURFACE_COLOR
            
            chat_list.controls.append(
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text(msg.get("sender", "Tu"), size=9, color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
                            ft.Text(msg["content"], color=color, size=14),
                        ], spacing=2),
                        bgcolor=bg,
                        padding=ft.Padding(12, 8, 12, 8),
                        border_radius=ft.BorderRadius(15, 15, 2, 15) if is_user else ft.BorderRadius(15, 15, 15, 2),
                        border=ft.Border.all(0.5, ACCENT_COLOR) if is_user else None,
                        width=page.window_width * 0.7
                    )
                ], alignment=align)
            )
        update_metriplectic_monitor()
        page.update()

    def send_click(e):
        target_fp = target_fp_input.value
        prompt    = msg_input.value

        if not target_fp:
            snack("Specify destination fingerprint")
            return

        if target_fp not in state["peer"].trusted_peers:
            snack("Target not trusted. Request handshake first.", ft.Colors.ORANGE_800)
            return

        if not prompt:
            snack("Message empty")
            return

        state["messages"].append({"role": "user", "sender": "Tu", "content": prompt})
        target_data = PeerDiscovery.resolve_peer(target_fp)
        if target_data:
            success = state["peer"].send_packet(target_data[0], target_data[1], prompt, target_fp)
            if success:
                msg_input.value = ""
            else:
                snack("Packet transmission failed")
        else:
            snack("Target address not in cache")
        update_chat_ui()

    # ── Tab 1: Metriplectic Console ───────────────────────────────────────────

    p2p_view = ft.Column(
        controls=[
            # Header Identity Card
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FINGERPRINT, color=ACCENT_COLOR, size=30),
                        ft.Column([
                            ft.Text("LOCAL IDENTITY", size=10, color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "\n".join([state["local_fp"][i:i+16] for i in range(0, len(state["local_fp"]), 16)]) 
                                if state["local_fp"] else "Inicializando...",
                                font_family="monospace", 
                                size=11, 
                                color=ACCENT_COLOR
                            )
                        ], spacing=0)
                    ]),
                    ft.Divider(height=10, color=ft.Colors.with_opacity(0.1, ACCENT_COLOR)),
                    ft.Row([
                        ft.Column([
                            ft.Text("H (Symplectic)", size=9, color=ACCENT_COLOR),
                            symplectic_bar,
                        ], expand=True),
                        ft.Column([
                            ft.Text("S (Metric)", size=9, color=ft.Colors.PURPLE_400),
                            metric_bar,
                        ], expand=True),
                    ], spacing=20)
                ]),
                padding=20,
                border_radius=20,
                bgcolor=SURFACE_COLOR,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ACCENT_COLOR)),
                shadow=ft.BoxShadow(blur_radius=20, color=SHADOW_COLOR)
            ),
            
            # Contacts & Requests
            ft.Text("NETWORK MESH", size=11, color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([
                    handshake_column,
                    contacts_column,
                ], scroll=ft.ScrollMode.AUTO, spacing=10),
                height=150,
            ),
            
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            
            # Chat Area
            ft.Text("SECURE CHANNEL", size=11, color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=chat_list,
                expand=True,
                bgcolor=SURFACE_COLOR,
                border_radius=20,
                border=ft.Border.all(0.5, ft.Colors.BLUE_GREY_900),
            ),
            
            # Input Area
            ft.Row([
                target_fp_input,
                ft.Container(width=5), # spacer
                msg_input,
                ft.FloatingActionButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    on_click=send_click
                )
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ],
        expand=True,
        visible=True,
        spacing=15
    )

    # ── Tab 2: QR Offline ─────────────────────────────────────────────────────

    qr_image_control = ft.Image(src="", width=250, height=250, fit=ft.BoxFit.CONTAIN)
    qr_counter_text  = ft.Text("0 / 0", color=ACCENT_COLOR, font_family="monospace")

    def animate_qr(max_loops: int = 3):
        if state["animating"] or not state["qr_frames_b64"]:
            return
        state["animating"] = True
        idx        = 0
        loops_done = 0
        total      = len(state["qr_frames_b64"])

        while state["animating"] and state["qr_frames_b64"]:
            qr_image_control.src_base64 = state["qr_frames_b64"][idx]
            qr_counter_text.value = (
                f"FRAME: {idx + 1}/{total} | LOOP: {loops_done + 1}/{max_loops}"
            )
            page.run_task(lambda: page.update())

            idx += 1
            if idx >= total:
                idx = 0
                loops_done += 1
                if loops_done >= max_loops:
                    break

            time.sleep(0.15)

        state["animating"] = False
        if state["qr_frames_b64"]:
            qr_image_control.src_base64 = state["qr_frames_b64"][0]
            qr_counter_text.value = f"READY: {total} FRAMES"
            page.run_task(lambda: page.update())

    def stop_animating():
        state["animating"] = False

    def pick_files_result(e):
        if not e.files:
            return
        file_path = e.files[0].path
        filename  = e.files[0].name
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            protocol = QRTransferProtocol(h7_index=state["h7_seed"], chunk_size=400)
            frames   = protocol.prepare_payload(file_bytes, filename)
            images   = protocol.generate_qr_images(frames)

            state["qr_frames_b64"] = []
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                state["qr_frames_b64"].append(base64.b64encode(buf.getvalue()).decode())

            snack(f"Payload fragmented into {len(frames)} units.", ft.Colors.GREEN_700)
            threading.Thread(target=animate_qr, daemon=True).start()

        except Exception as ex:
            snack(f"Error: {str(ex)}")
        page.update()

    file_picker = ft.FilePicker()
    file_picker.on_result = pick_files_result
    page.overlay.append(file_picker)

    def scan_qr_click(e):
        snack("Accessing Camera...", ft.Colors.BLUE_700)

        def _scan():
            protocol = QRTransferProtocol(h7_index=state["h7_seed"], chunk_size=400)
            file_bytes, filename = protocol.scan_animated_qr_from_camera()

            if file_bytes and filename:
                out_path = os.path.join(
                    os.path.expanduser("~"), "Downloads", "bimo_rec_" + filename
                )
                try:
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(file_bytes)
                    msg = f"Saved: {out_path}"
                except Exception:
                    with open(filename, "wb") as f:
                        f.write(file_bytes)
                    msg = f"Saved: {filename}"
                snack(msg, ft.Colors.GREEN_700)
            else:
                snack("Scanning canceled/failed.")

        threading.Thread(target=_scan, daemon=True).start()

    qr_view = ft.Column(
        controls=[
            ft.Text("PHYSICAL TRANSFER", size=20, color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
            ft.Divider(color=ACCENT_COLOR),
            
            ft.Container(
                content=ft.Column([
                    ft.Text("TRANSMIT PAYLOAD", weight=ft.FontWeight.BOLD),
                    ft.FilledButton(
                        "Prepare File",
                        icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                        on_click=lambda _: file_picker.pick_files(),
                        style=ft.ButtonStyle(bgcolor=ACCENT_COLOR, color=BG_COLOR)
                    ),
                    ft.Container(
                        content=ft.Column([
                            qr_image_control, 
                            qr_counter_text
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=10,
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ACCENT_COLOR)),
                        border_radius=15,
                    )
                ], spacing=15),
                padding=20,
                bgcolor=SURFACE_COLOR,
                border_radius=20
            ),

            ft.Container(
                content=ft.Column([
                    ft.Text("RECEIVE DATA", weight=ft.FontWeight.BOLD),
                    ft.FilledButton(
                        "Launch Scanner",
                        icon=ft.Icons.QR_CODE_SCANNER_ROUNDED,
                        on_click=scan_qr_click,
                        width=float("inf"),
                        style=ft.ButtonStyle(bgcolor=ft.Colors.WHITE24, color=ft.Colors.WHITE)
                    ),
                ], spacing=15),
                padding=20,
                bgcolor=SURFACE_COLOR,
                border_radius=20
            ),
        ],
        expand=True,
        visible=False,
        scroll=ft.ScrollMode.AUTO,
        spacing=20
    )

    # ── Navigation ────────────────────────────────────────────────────────────

    def nav_change(e):
        p2p_view.visible = (e.control.selected_index == 0)
        qr_view.visible  = (e.control.selected_index == 1)
        if not qr_view.visible:
            stop_animating()
        page.update()

    nav_bar = ft.NavigationBar(
        bgcolor=SURFACE_COLOR,
        selected_index=0,
        indicator_color=ACCENT_COLOR,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.SUBDIRECTORY_ARROW_RIGHT_ROUNDED,
                selected_icon=ft.Icons.DASHBOARD_ROUNDED,
                label="Console"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.QR_CODE_2_ROUNDED,
                selected_icon=ft.Icons.QR_CODE_ROUNDED,
                label="Physical"
            ),
        ]
    )
    nav_bar.on_change = nav_change
    page.navigation_bar = nav_bar

    page.add(ft.SafeArea(ft.Column([p2p_view, qr_view], expand=True)))


if __name__ == "__main__":
    ft.run(main)
