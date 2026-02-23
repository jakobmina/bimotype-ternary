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

    BG_COLOR      = "#0b0e14"
    ACCENT_COLOR  = "#00d4ff"
    SURFACE_COLOR = "#161b22"

    page.bgcolor = BG_COLOR

    state = {
        "peer": None,
        "local_fp": None,
        "messages": [],
        "handshake_requests": [],
        "target_fp": "",
        "h7_seed": 42,
        "qr_frames_b64": [],
        "animating": False
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
        page.run_task(lambda: update_contacts_ui())

    threading.Thread(target=init_peer_async, daemon=True).start()

    # ── Shared controls ───────────────────────────────────────────────────────

    chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)

    msg_input = ft.TextField(
        hint_text="Escribe tu mensaje...",
        expand=True,
        border_color=ACCENT_COLOR,
        color=ACCENT_COLOR,
        bgcolor=SURFACE_COLOR
    )

    target_fp_input = ft.TextField(
        label="Fingerprint de Destino",
        hint_text="Huella del receptor...",
        border_color=ACCENT_COLOR,
        color=ACCENT_COLOR,
        bgcolor=SURFACE_COLOR
    )

    handshake_column = ft.Column(spacing=5)
    contacts_column = ft.Column(spacing=5)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def snack(text, color=ft.Colors.RED_700):
        page.snack_bar = ft.SnackBar(ft.Text(text), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def update_contacts_ui():
        contacts_column.controls.clear()
        trusted = state["peer"].trusted_peers
        if not trusted:
            contacts_column.controls.append(ft.Text("No hay contactos de confianza", size=12, italic=True, color=ft.Colors.GREY_500))
        else:
            for t_fp in list(trusted):
                def set_target(e, fp=t_fp):
                    target_fp_input.value = fp
                    page.update()
                    snack(f"Objetivo: {fp[:8]}...", ft.Colors.BLUE_700)

                contacts_column.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK, color=ACCENT_COLOR, size=16),
                            ft.Text(f"{t_fp[:16]}...", color=ACCENT_COLOR, expand=True),
                            ft.IconButton(ft.Icons.CHAT, on_click=set_target, icon_color=ACCENT_COLOR)
                        ]),
                        bgcolor=SURFACE_COLOR,
                        padding=5,
                        border_radius=5,
                        on_click=set_target
                    )
                )

        # Sección de Descubrimiento (solo si hay nuevos pares)
        discovered_controls = []
        peers = PeerDiscovery.get_all_peers()
        for fp, data in peers.items():
            if fp != state["local_fp"] and fp not in trusted:
                def request_hs(e, target_fp=fp, host=data["host"], port=data["port"]):
                    state["peer"].request_handshake(host, port)
                    snack(f"Handshake enviado a {target_fp[:8]}", ft.Colors.ORANGE_700)

                discovered_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PERSON_ADD_OUTLINED, color=ft.Colors.GREY_400, size=16),
                            ft.Text(f"Disponible: {fp[:8]}...", color=ft.Colors.GREY_400, expand=True),
                            ft.IconButton(ft.Icons.HANDSHAKE, on_click=request_hs, icon_color=ft.Colors.ORANGE_400)
                        ]),
                        bgcolor=SURFACE_COLOR,
                        padding=5,
                        border_radius=5
                    )
                )

        if discovered_controls:
            contacts_column.controls.append(
                ft.ExpansionTile(
                    title=ft.Text("Descubrir nuevos pares", size=12, color=ft.Colors.GREY_400),
                    controls=discovered_controls,
                    text_color=ft.Colors.GREY_400,
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
                snack(f"Conexión establecida con {fp[:8]}", ft.Colors.GREEN_700)
                update_handshake_ui()
                update_contacts_ui()

            def ign_click(e, fp=req_fp):
                state["handshake_requests"].remove(fp)
                update_handshake_ui()

            row = ft.Row([
                ft.Text(f"Solicitud: {req_fp[:8]}..."),
                ft.IconButton(ft.Icons.CHECK, on_click=acc_click, icon_color=ft.Colors.GREEN_400),
                ft.IconButton(ft.Icons.CLOSE, on_click=ign_click, icon_color=ft.Colors.RED_400),
            ])
            handshake_column.controls.append(
                ft.Container(
                    content=row,
                    bgcolor=ft.Colors.ORANGE_900,
                    padding=5,
                    border_radius=5
                )
            )
        page.update()

    def update_chat_ui():
        chat_list.controls.clear()
        for msg in state["messages"]:
            is_user = msg["role"] == "user"
            align  = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
            color  = ACCENT_COLOR if is_user else ft.Colors.WHITE
            bg     = "#1a1f29"    if is_user else SURFACE_COLOR
            border = ft.Border.all(1, ACCENT_COLOR) if is_user else None

            chat_list.controls.append(
                ft.Row([
                    ft.Container(
                        content=ft.Text(
                            f'[{msg.get("sender", "Tu")}] {msg["content"]}',
                            color=color
                        ),
                        bgcolor=bg,
                        padding=10,
                        border_radius=10,
                        border=border
                    )
                ], alignment=align)
            )
        page.update()

    def send_click(e):
        target_fp = target_fp_input.value
        prompt    = msg_input.value

        if not target_fp:
            snack("Introduce un Fingerprint de destino")
            return

        if target_fp not in state["peer"].trusted_peers:
            snack("Aún no es de confianza. Solicita Handshake primero.")
            return

        if not prompt:
            snack("Escribe un mensaje")
            return

        state["messages"].append({"role": "user", "sender": "Tu", "content": prompt})
        target_data = PeerDiscovery.resolve_peer(target_fp)
        if target_data:
            success = state["peer"].send_packet(target_data[0], target_data[1], prompt, target_fp)
            if success:
                msg_input.value = ""
            else:
                snack("Error al enviar el paquete")
        else:
            snack("Dirección del contacto no encontrada en caché")
        update_chat_ui()

    # ── Tab 1: P2P ────────────────────────────────────────────────────────────

    p2p_view = ft.Column(
        controls=[
            ft.Text("Identidad Local", color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Text(
                    state["local_fp"],
                    selectable=True,
                    color=ACCENT_COLOR,
                    font_family="monospace"
                ),
                bgcolor=SURFACE_COLOR,
                padding=10,
                border_radius=5,
                border=ft.Border.all(1, ACCENT_COLOR)
            ),
            ft.Text("Contactos y Solicitudes", color=ACCENT_COLOR, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([
                    handshake_column,
                    contacts_column,
                ], scroll=ft.ScrollMode.AUTO),
                height=200,
            ),
            target_fp_input,
            ft.Container(
                content=chat_list,
                expand=True,
                border=ft.Border.all(1, ft.Colors.BLUE_GREY_800),
                border_radius=5,
                padding=5
            ),
            ft.Row([
                msg_input,
                ft.IconButton(
                    icon=ft.Icons.SEND,
                    on_click=send_click,
                    icon_color=ACCENT_COLOR
                )
            ])
        ],
        expand=True,
        visible=True
    )

    # ── Tab 2: QR Offline ─────────────────────────────────────────────────────

    qr_image_control = ft.Image(src="", width=300, height=300, fit=ft.BoxFit.CONTAIN)
    qr_counter_text  = ft.Text("0 / 0", color=ACCENT_COLOR)

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
                f"{idx + 1} / {total}  "
                f"(ciclo {loops_done + 1}/{max_loops})"
            )
            page.run_task(lambda: page.update())

            idx += 1
            if idx >= total:          # completó un ciclo completo
                idx = 0
                loops_done += 1
                if loops_done >= max_loops:
                    break             # salir como GIF que terminó sus repeticiones

            time.sleep(0.15)

        # Al terminar: congelar en primer frame y liberar el flag
        state["animating"] = False
        if state["qr_frames_b64"]:
            qr_image_control.src_base64 = state["qr_frames_b64"][0]
            qr_counter_text.value = (
                f"✓ {total} frames  ({max_loops} ciclos completados)"
            )
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

            snack(f"Archivo dividido en {len(frames)} QRs.", ft.Colors.GREEN_700)
            threading.Thread(target=animate_qr, daemon=True).start()

        except Exception as ex:
            snack(f"Error: {str(ex)}")
        page.update()

    file_picker = ft.FilePicker()
    file_picker.on_result = pick_files_result
    page.overlay.append(file_picker)

    def scan_qr_click(e):
        snack("Abriendo escáner...", ft.Colors.BLUE_700)

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
                    msg = f"Guardado en {out_path}"
                except Exception:
                    with open(filename, "wb") as f:
                        f.write(file_bytes)
                    msg = f"Guardado como {filename}"
                snack(msg, ft.Colors.GREEN_700)
            else:
                snack("Escaneo cancelado o fallido.")

        threading.Thread(target=_scan, daemon=True).start()
    qr_view = ft.Column(
        controls=[
            ft.Text(
                "Transferencia Offline",
                color=ACCENT_COLOR,
                weight=ft.FontWeight.BOLD,
                size=20
            ),
            ft.Divider(color=ACCENT_COLOR),
            ft.Text("Emitir Archivo 📤", color=ft.Colors.WHITE),
            ft.FilledButton(
                content=ft.Text("Seleccionar y Emitir"),
                icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda _: file_picker.pick_files()
            ),
            ft.Container(
                content=ft.Column(
                    [qr_image_control, qr_counter_text],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                alignment=ft.Alignment(0, 0),
                padding=20
            ),
            ft.Divider(color=ACCENT_COLOR),
            ft.Text("Recibir Archivo 📥", color=ft.Colors.WHITE),
            ft.FilledButton(
                content=ft.Text("Abrir Escáner"),
                icon=ft.Icons.QR_CODE_SCANNER,
                on_click=scan_qr_click
            ),
        ],
        expand=True,
        visible=False,
        scroll=ft.ScrollMode.AUTO
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
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.MESSAGE_OUTLINED,
                selected_icon=ft.Icons.MESSAGE,
                label="P2P Chat"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.QR_CODE_SCANNER_OUTLINED,
                selected_icon=ft.Icons.QR_CODE,
                label="QR Offline"
            ),
        ]
    )
    nav_bar.on_change = nav_change
    page.navigation_bar = nav_bar

    page.add(ft.SafeArea(ft.Column([p2p_view, qr_view], expand=True)))


if __name__ == "__main__":
    ft.run(main)
