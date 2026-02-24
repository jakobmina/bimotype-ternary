import pytest
from unittest.mock import MagicMock, patch
import flet as ft
from bimotype_ternary.mobile_gui import main

def test_mobile_gui_state_initialization():
    """Test that the initial state of the mobile GUI is correctly defined."""
    page = MagicMock(spec=ft.Page)
    page.overlay = []
    
    # We don't want to actually run the peer init thread for this test
    with patch("threading.Thread") as mock_thread:
        main(page)
        
        # Check initial properties
        assert page.title == "BiMoType Metriplectic Console"
        assert page.theme_mode == ft.ThemeMode.DARK
        
        # Verify nav bar is set
        assert page.navigation_bar is not None
        assert len(page.navigation_bar.destinations) == 2

def test_metriplectic_monitor_logic():
    """Test that the metriplectic monitor bars exist and have initial values."""
    page = MagicMock(spec=ft.Page)
    page.overlay = []
    
    with patch("threading.Thread"):
        main(page)
        
        # Find the Metriplectic Monitor bars in the view
        # The first view added to page is ft.SafeArea(ft.Column([p2p_view, qr_view]))
        safe_area = page.add.call_args[0][0]
        column = safe_area.content
        p2p_view = column.controls[0]
        
        # The first control in p2p_view is the Identity Card Container
        identity_card = p2p_view.controls[0]
        card_content = identity_card.content
        
        # The third control in card_content is the Row with Symplectic and Metric bars
        monitor_row = card_content.controls[2]
        
        # Verify the progress bars are there
        # Column(H) and Column(S)
        assert len(monitor_row.controls) == 2
        col_h = monitor_row.controls[0]
        col_s = monitor_row.controls[1]
        
        bar_h = col_h.controls[1]
        bar_s = col_s.controls[1]
        
        assert isinstance(bar_h, ft.ProgressBar)
        assert isinstance(bar_s, ft.ProgressBar)
        assert bar_h.value == 0.5
        assert bar_s.value == 0.5
