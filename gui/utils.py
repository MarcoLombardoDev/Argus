import types
import customtkinter as ctk

def apply_binance_tab_style(segmented_button: ctk.CTkSegmentedButton):
    """
    Patches a CTkSegmentedButton to ensure that selected tabs/segments 
    have dark text (#181a20) and unselected ones have white text.
    """
    orig_select = segmented_button._select_button_by_value
    orig_unselect = segmented_button._unselect_button_by_value

    def new_select(self, value):
        orig_select(value)
        if value in self._buttons_dict:
            self._buttons_dict[value].configure(text_color="#181a20")

    def new_unselect(self, value):
        orig_unselect(value)
        if value in self._buttons_dict:
            self._buttons_dict[value].configure(text_color="white")

    segmented_button._select_button_by_value = types.MethodType(new_select, segmented_button)
    segmented_button._unselect_button_by_value = types.MethodType(new_unselect, segmented_button)

    # Immediately apply style to current buttons
    for val, btn in segmented_button._buttons_dict.items():
        if val == segmented_button._current_value:
            btn.configure(text_color="#181a20")
        else:
            btn.configure(text_color="white")
