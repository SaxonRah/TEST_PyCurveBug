#!/usr/bin/env python3
"""
PyCurveBug - Curve Viewer for vintageTEK CurveBug (Pyglet Edition)

REQUIRED:
    pyglet
    pyserial

Minimal dependencies version - no PyGame, no NumPy

Features:
    - Full settings window with tabs
    - Color customization with RGB sliders
    - Keybind configuration
    - Window size settings
    - Serial port configuration
"""

import serial
import serial.tools.list_ports

import pyglet
from pyglet import shapes
from pyglet.window import key, mouse

import struct
import json
import os
import time

# Constants
ADC_MAX = 2800
ADC_ORIGIN = 2048
OUTPUT_DEBUG_TEXT = False


def debug_print(contents: str = None):
    if OUTPUT_DEBUG_TEXT:
        print(contents)


def list_min(lst):
    """Minimum of list without numpy"""
    return min(lst) if lst else 0


def list_max(lst):
    """Maximum of list without numpy"""
    return max(lst) if lst else 0


def list_mean(lst):
    """Mean of list without numpy"""
    return sum(lst) / len(lst) if lst else 0


class ConfigManager:
    """Manages application configuration and settings"""

    DEFAULT_CONFIG = {
        'serial_port': 'COM4',
        'window_width': 1080,
        'window_height': 1080,
        'colors': {
            'background': [0, 0, 0],
            'dut1_trace': [50, 150, 255],
            'dut2_trace': [255, 50, 50],
            'dut1_dimmed': [25, 75, 128],
            'dut2_dimmed': [128, 25, 25],
            'grid_background': [30, 30, 30],
            'grid': [50, 50, 50],
            'crosshair': [255, 255, 50],
            'label': [200, 200, 200],
            'axis_title': [255, 255, 255],
            'border': [100, 100, 100],
            'dut_voltage': [50, 255, 150],
        },
        'keybinds': {
            'quit': 'q',
            'pause': 'p',
            'single_channel': 's',
            'auto_scale': 'a',
            'fit_window': 'f',
            'reset_view': 'r',
            'cycle_mode': 'space',
            'settings': 'f1',
        }
    }

    def __init__(self, config_file='curvebug_config.json'):
        self.config_file = config_file
        self.config = self._deep_copy(self.DEFAULT_CONFIG)
        self.load_config()

    def _deep_copy(self, d):
        """Deep copy dictionary"""
        if isinstance(d, dict):
            return {k: self._deep_copy(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._deep_copy(v) for v in d]
        return d

    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    self._deep_update(self.config, saved_config)
                debug_print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                debug_print(f"Error loading config: {e}, using defaults")

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            debug_print(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            debug_print(f"Error saving config: {e}")
            return False

    def _deep_update(self, base_dict, update_dict):
        """Recursively update nested dictionary"""
        for temp_key, value in update_dict.items():
            if temp_key in base_dict and isinstance(base_dict[temp_key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[temp_key], value)
            else:
                base_dict[temp_key] = value

    def get(self, *keys):
        """Get nested config value"""
        value = self.config
        for k in keys:
            value = value.get(k)
            if value is None:
                return None
        return value

    def set(self, value, *keys):
        """Set nested config value"""
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value


class Button:
    """Simple button widget for Pyglet"""

    def __init__(self, x, y, width, height, text, color, text_color):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.color = color
        self.hover_color = tuple(min(c + 30, 255) for c in color)
        self.text_color = text_color
        self.hovered = False

    def contains(self, mx, my):
        """Check if point is inside button"""
        return self.x <= mx <= self.x + self.width and self.y <= my <= self.y + self.height

    def update_hover(self, mx, my):
        """Update hover state"""
        self.hovered = self.contains(mx, my)

    def draw(self):
        """Draw the button"""
        color = self.hover_color if self.hovered else self.color
        rect = shapes.Rectangle(self.x, self.y, self.width, self.height, color=color)
        rect.draw()

        border = shapes.Box(self.x, self.y, self.width, self.height, thickness=2, color=self.text_color)
        border.draw()

        label = pyglet.text.Label(
            self.text,
            font_size=14,
            x=self.x + self.width // 2,
            y=self.y + self.height // 2,
            anchor_x='center',
            anchor_y='center',
            color=self.text_color + (255,)
        )
        label.draw()


class InputBox:
    """Text input box for Pyglet"""

    def __init__(self, x, y, width, height, text):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0

    def contains(self, mx, my):
        """Check if point is inside input box"""
        return self.x <= mx <= self.x + self.width and self.y <= my <= self.y + self.height

    def update(self, dt):
        """Update cursor blink"""
        if self.active:
            self.cursor_timer += dt
            if self.cursor_timer > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0

    def draw(self):
        """Draw the input box"""
        color = (255, 255, 255) if self.active else (100, 100, 100)

        bg = shapes.Rectangle(self.x, self.y, self.width, self.height, color=(30, 30, 30))
        bg.draw()

        border = shapes.Box(self.x, self.y, self.width, self.height, thickness=2, color=color)
        border.draw()

        label = pyglet.text.Label(
            self.text,
            font_size=14,
            x=self.x + 5,
            y=self.y + self.height // 2,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        label.draw()

        # Cursor
        if self.active and self.cursor_visible:
            # Get text width for cursor position
            temp_label = pyglet.text.Label(self.text, font_size=14)
            cursor_x = self.x + 5 + temp_label.content_width
            cursor = shapes.Line(
                cursor_x, self.y + 5,
                cursor_x, self.y + self.height - 5,
                color=(255, 255, 255)
            )
            cursor.draw()

    def handle_click(self, mx, my):
        """Handle mouse click"""
        self.active = self.contains(mx, my)
        if self.active:
            self.cursor_visible = True
            self.cursor_timer = 0

    def handle_text(self, text):
        """Handle text input"""
        if self.active:
            self.text += text

    def handle_backspace(self):
        """Handle backspace"""
        if self.active and self.text:
            self.text = self.text[:-1]


class ColorPickerDialog:
    """Color picker with RGB sliders"""

    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.color = [0, 0, 0]
        self.original_color = [0, 0, 0]
        self.active = False

        self.width = 400
        self.height = 250
        self.x = (screen_width - self.width) // 2
        self.y = (screen_height - self.height) // 2

        self.slider_width = 250
        self.slider_height = 20
        self.dragging = -1

        self._create_buttons()

    def _create_buttons(self):
        """Create OK and Cancel buttons"""
        self.ok_button = Button(
            self.x + self.width - 220,
            self.y + 20,
            100, 40,
            'OK',
            (50, 255, 150),
            (255, 255, 255)
        )
        self.cancel_button = Button(
            self.x + self.width - 110,
            self.y + 20,
            100, 40,
            'Cancel',
            (255, 50, 50),
            (255, 255, 255)
        )

    def update_position(self, screen_width, screen_height):
        """Update position when screen resizes"""
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.x = (screen_width - self.width) // 2
        self.y = (screen_height - self.height) // 2
        self._create_buttons()

    def show(self, color):
        """Show the color picker"""
        self.color = list(color)
        self.original_color = list(color)
        self.active = True

    def hide(self):
        """Hide the color picker"""
        self.active = False
        self.dragging = -1

    def draw(self):
        """Draw the color picker"""
        if not self.active:
            return

        # Semi-transparent overlay
        overlay = shapes.Rectangle(0, 0, self.screen_width, self.screen_height, color=(0, 0, 0))
        overlay.opacity = 200
        overlay.draw()

        # Dialog background
        dialog_bg = shapes.Rectangle(self.x, self.y, self.width, self.height, color=(30, 30, 30))
        dialog_bg.draw()

        dialog_border = shapes.Box(self.x, self.y, self.width, self.height, thickness=3, color=(255, 255, 255))
        dialog_border.draw()

        # Title
        title = pyglet.text.Label(
            'Choose Color',
            font_size=16,
            x=self.x + 20,
            y=self.y + self.height - 30,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        title.draw()

        # RGB sliders
        labels = ['Red:', 'Green:', 'Blue:']
        slider_start_y = self.y + self.height - 80

        for i, label_text in enumerate(labels):
            y_pos = slider_start_y - i * 45

            # Label
            label = pyglet.text.Label(
                label_text,
                font_size=14,
                x=self.x + 30,
                y=y_pos + self.slider_height // 2,
                anchor_x='left',
                anchor_y='center',
                color=(255, 255, 255, 255)
            )
            label.draw()

            # Slider background
            slider_bg = shapes.Rectangle(
                self.x + 100, y_pos,
                self.slider_width, self.slider_height,
                color=(50, 50, 50)
            )
            slider_bg.draw()

            slider_border = shapes.Box(
                self.x + 100, y_pos,
                self.slider_width, self.slider_height,
                thickness=1, color=(100, 100, 100)
            )
            slider_border.draw()

            # Slider fill
            fill_width = int((self.color[i] / 255) * self.slider_width)
            slider_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
            fill = shapes.Rectangle(
                self.x + 100, y_pos,
                fill_width, self.slider_height,
                color=slider_colors[i]
            )
            fill.draw()

            # Value text
            value_text = pyglet.text.Label(
                str(self.color[i]),
                font_size=14,
                x=self.x + 100 + self.slider_width + 10,
                y=y_pos + self.slider_height // 2,
                anchor_x='left',
                anchor_y='center',
                color=(255, 255, 255, 255)
            )
            value_text.draw()

        # Color preview
        preview_size = 80
        preview_x = self.x + self.width - preview_size - 30
        preview_y = slider_start_y - 40

        preview = shapes.Rectangle(
            preview_x, preview_y,
            preview_size, preview_size,
            color=tuple(self.color)
        )
        preview.draw()

        preview_border = shapes.Box(
            preview_x, preview_y,
            preview_size, preview_size,
            thickness=2, color=(255, 255, 255)
        )
        preview_border.draw()

        # Preview label
        preview_label = pyglet.text.Label(
            'Preview',
            font_size=12,
            x=preview_x,
            y=preview_y + preview_size + 10,
            anchor_x='left',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        preview_label.draw()

        # Buttons
        self.ok_button.draw()
        self.cancel_button.draw()

    def handle_click(self, mx, my):
        """Handle mouse click - returns 'ok', 'cancel', or None"""
        if not self.active:
            return None

        # Check buttons
        if self.ok_button.contains(mx, my):
            self.hide()
            return 'ok'

        if self.cancel_button.contains(mx, my):
            self.color = self.original_color.copy()
            self.hide()
            return 'cancel'

        # Check sliders
        slider_start_y = self.y + self.height - 80
        for i in range(3):
            y_pos = slider_start_y - i * 45
            if (self.x + 100 <= mx <= self.x + 100 + self.slider_width and
                    y_pos <= my <= y_pos + self.slider_height):
                self.dragging = i
                self._update_slider(i, mx)
                return None

        return None

    def handle_release(self):
        """Handle mouse release"""
        self.dragging = -1

    def handle_motion(self, mx, my):
        """Handle mouse motion"""
        if self.dragging != -1:
            self._update_slider(self.dragging, mx)

        # Update button hover states
        self.ok_button.update_hover(mx, my)
        self.cancel_button.update_hover(mx, my)

    def _update_slider(self, index, mouse_x):
        """Update slider value"""
        slider_x = self.x + 100
        relative_x = max(0, min(mouse_x - slider_x, self.slider_width))
        self.color[index] = int((relative_x / self.slider_width) * 255)


class ColorSwatch:
    """Clickable color swatch"""

    def __init__(self, x, y, width, height, color, label):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = list(color)
        self.label = label
        self.hovered = False

    def contains(self, mx, my):
        """Check if click is on color box"""
        color_box_x = self.x + self.width - 100
        return (color_box_x <= mx <= color_box_x + 100 and
                self.y <= my <= self.y + 35)

    def update_hover(self, mx, my):
        """Update hover state"""
        self.hovered = self.contains(mx, my)

    def draw(self):
        """Draw the color swatch"""
        # Label
        label = pyglet.text.Label(
            self.label,
            font_size=14,
            x=self.x,
            y=self.y + 20,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        label.draw()

        # Color box
        color_box_x = self.x + self.width - 100
        color_box = shapes.Rectangle(
            color_box_x, self.y,
            100, 35,
            color=tuple(self.color)
        )
        color_box.draw()

        border_color = (255, 255, 255) if self.hovered else (100, 100, 100)
        border = shapes.Box(
            color_box_x, self.y,
            100, 35,
            thickness=2, color=border_color
        )
        border.draw()

    def update_color(self, color):
        """Update the color"""
        self.color = list(color)


class SettingsWindow:
    """Full-screen settings overlay"""

    def __init__(self, config_manager, screen_width, screen_height):
        self.config = config_manager
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.active = False
        self.tab = 0  # 0=Display, 1=Colors, 2=Keybinds, 3=Serial

        self.color_picker = ColorPickerDialog(screen_width, screen_height)
        self.editing_color = None

        self._calculate_layout()
        self._init_widgets()

    def _calculate_layout(self):
        """Calculate layout for full-screen settings"""
        self.width = self.screen_width
        self.height = self.screen_height

        self.margin_x = max(40, int(self.width * 0.05))
        self.margin_y = max(30, int(self.height * 0.05))

        self.content_x = self.margin_x
        self.content_y = self.margin_y + self.height/2
        self.content_width = self.width - 2 * self.margin_x
        self.content_height = self.height - self.content_y - 100

    def update_screen_size(self, width, height):
        """Update layout when screen resizes"""
        self.screen_width = width
        self.screen_height = height
        self._calculate_layout()
        self._init_widgets()
        self.color_picker.update_position(width, height)

    def _init_widgets(self):
        """Initialize UI widgets"""
        # Tab buttons
        tab_width = max(120, min(180, (self.content_width - 60) // 4))
        tab_spacing = 15
        total_tab_width = 4 * tab_width + 3 * tab_spacing
        tab_start_x = (self.width - total_tab_width) // 2
        tab_y = self.content_y + self.height/3

        self.tab_buttons = [
            Button(tab_start_x + i * (tab_width + tab_spacing), tab_y, tab_width, 45,
                   text, (50, 50, 50), (255, 255, 255))
            for i, text in enumerate(['Display', 'Colors', 'Keybinds', 'Serial'])
        ]

        # Column layout
        col_width = min(400, self.content_width // 2 - 40)
        col1_x = self.content_x + 40
        col2_x = self.content_x + self.content_width // 2 + 20

        # Display settings
        self.width_input = InputBox(
            col1_x + 180, self.content_y - 30, 150, 40,
            str(self.config.get('window_width'))
        )
        self.height_input = InputBox(
            col1_x + 180, self.content_y - 90, 150, 40,
            str(self.config.get('window_height'))
        )

        # Color swatches
        self.color_swatches = {}
        color_configs = [
            ('background', 'Background'),
            ('dut1_trace', 'DUT1 Trace (Blue)'),
            ('dut2_trace', 'DUT2 Trace (Red)'),
            ('dut1_dimmed', 'DUT1 Dimmed'),
            ('dut2_dimmed', 'DUT2 Dimmed'),
            ('grid_background', 'Grid Background'),
            ('grid', 'Grid Lines'),
            ('crosshair', 'Crosshair'),
            ('label', 'Axis Labels'),
            ('axis_title', 'Axis Titles'),
            ('border', 'Border'),
            ('dut_voltage', 'DUT Voltage'),
        ]

        items_per_col = (len(color_configs) + 1) // 2
        swatch_width = min(500, (self.content_width - 80) // 2)

        for i, (key, label) in enumerate(color_configs):
            color = self.config.get('colors', key)
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y - 40 + row * 50

            swatch = ColorSwatch(x, y, swatch_width, 40, color, label)
            self.color_swatches[key] = swatch

        # Keybind inputs
        self.keybind_inputs = {}
        self.keybind_labels = {
            'quit': 'Quit:',
            'pause': 'Pause:',
            'single_channel': 'Single Channel:',
            'auto_scale': 'Auto Scale:',
            'fit_window': 'Fit Window:',
            'reset_view': 'Reset View:',
            'cycle_mode': 'Cycle Mode:',
            'settings': 'Settings:',
        }

        keybind_names = list(self.config.get('keybinds').keys())
        items_per_col = (len(keybind_names) + 1) // 2

        for i, name in enumerate(keybind_names):
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y - 40 + row * 60

            self.keybind_inputs[name] = InputBox(
                x + 200, y, 120, 40,
                self.config.get('keybinds', name)
            )

        # Serial port input
        self.serial_input = InputBox(
            col1_x + 180, self.content_y ,
            min(400, self.content_width - 300), 40,
            self.config.get('serial_port')
        )

        # Bottom buttons
        button_width = 140
        button_height = 50
        button_spacing = 20
        button_y = 30
        total_button_width = 2 * button_width + button_spacing
        button_start_x = (self.width - total_button_width) // 2

        self.save_button = Button(
            button_start_x, button_y,
            button_width, button_height,
            'Save',
            (50, 255, 150),
            (255, 255, 255)
        )
        self.cancel_button = Button(
            button_start_x + button_width + button_spacing, button_y,
            button_width, button_height,
            'Cancel',
            (255, 50, 50),
            (255, 255, 255)
        )

    def show(self):
        """Show the settings window"""
        self.active = True

    def hide(self):
        """Hide the settings window"""
        self.active = False

    def update(self, dt):
        """Update animations"""
        if not self.active:
            return

        self.width_input.update(dt)
        self.height_input.update(dt)
        for input_box in self.keybind_inputs.values():
            input_box.update(dt)
        self.serial_input.update(dt)

    def draw(self):
        """Draw the settings window"""
        if not self.active:
            return

        # Full screen background
        bg = shapes.Rectangle(0, 0, self.width, self.height, color=(0, 0, 0))
        bg.draw()

        # Title bar
        title_bar = shapes.Rectangle(0, self.height - 60, self.width, 60, color=(30, 30, 30))
        title_bar.draw()

        title_line = shapes.Line(0, self.height - 60, self.width, self.height - 60, color=(100, 100, 100))
        title_line.draw()

        # Title
        tab_names = ['Display Settings', 'Color Settings', 'Keyboard Shortcuts', 'Serial Port Configuration']
        title = pyglet.text.Label(
            tab_names[self.tab],
            font_size=24,
            x=self.width // 2,
            y=self.height - 30,
            anchor_x='center',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        title.draw()

        # Tab buttons
        for i, button in enumerate(self.tab_buttons):
            if i == self.tab:
                button.color = (50, 150, 255)
            else:
                button.color = (50, 50, 50)
            button.draw()

        # Draw content based on active tab
        if self.tab == 0:
            self._draw_display_settings()
        elif self.tab == 1:
            self._draw_color_settings()
        elif self.tab == 2:
            self._draw_keybind_settings()
        elif self.tab == 3:
            self._draw_serial_settings()

        # Bottom buttons
        self.save_button.draw()
        self.cancel_button.draw()

        # Instructions
        instruction = pyglet.text.Label(
            "ESC to cancel  |  Click Save to apply changes",
            font_size=12,
            x=self.width // 2,
            y=90,
            anchor_x='center',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        instruction.draw()

        # Color picker on top
        self.color_picker.draw()

    def _draw_display_settings(self):
        """Draw display settings tab"""
        col1_x = self.content_x + 40
        y = self.content_y + 30

        label1 = pyglet.text.Label(
            'Window Width:',
            font_size=14,
            x=col1_x,
            y=y + 20,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        label1.draw()
        self.width_input.draw()

        label2 = pyglet.text.Label(
            'Window Height:',
            font_size=14,
            x=col1_x,
            y=y + 80,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        label2.draw()
        self.height_input.draw()

        # Info box
        info_y = y + 150
        info_bg = shapes.Rectangle(
            col1_x, info_y,
            self.content_width - 80, 80,
            color=(30, 30, 30)
        )
        info_bg.draw()

        info_border = shapes.Box(
            col1_x, info_y,
            self.content_width - 80, 80,
            thickness=2, color=(255, 255, 50)
        )
        info_border.draw()

        info_text = pyglet.text.Label(
            'Note: Window size changes require application restart',
            font_size=14,
            x=col1_x + 20,
            y=info_y + 50,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 50, 255)
        )
        info_text.draw()

        info_text2 = pyglet.text.Label(
            'You can also resize the window by dragging the window edges',
            font_size=11,
            x=col1_x + 20,
            y=info_y + 20,
            anchor_x='left',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        info_text2.draw()

    def _draw_color_settings(self):
        """Draw color settings tab"""
        for swatch in self.color_swatches.values():
            swatch.draw()

        # Info box
        info_y = self.content_y + self.content_height - 80
        info_bg = shapes.Rectangle(
            self.content_x + 40, info_y,
            self.content_width - 80, 45,
            color=(30, 30, 30)
        )
        info_bg.draw()

        info_border = shapes.Box(
            self.content_x + 40, info_y,
            self.content_width - 80, 45,
            thickness=2, color=(50, 150, 255)
        )
        info_border.draw()

        info_text = pyglet.text.Label(
            'Click any color box to customize',
            font_size=14,
            x=self.content_x + 60,
            y=info_y + 23,
            anchor_x='left',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        info_text.draw()

    def _draw_keybind_settings(self):
        """Draw keybind settings tab"""
        col1_x = self.content_x + 40
        col2_x = self.content_x + self.content_width // 2 + 20

        keybind_names = list(self.keybind_inputs.keys())
        items_per_col = (len(keybind_names) + 1) // 2

        for i, name in enumerate(keybind_names):
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y + 20 + row * 60

            label_text = self.keybind_labels.get(name, name + ':')
            label = pyglet.text.Label(
                label_text,
                font_size=14,
                x=x,
                y=y - 45,
                anchor_x='left',
                anchor_y='center',
                color=(255, 255, 255, 255)
            )
            label.draw()

            if name in self.keybind_inputs:
                self.keybind_inputs[name].draw()

        # Info box
        info_y = self.content_y + self.content_height - 100
        info_bg = shapes.Rectangle(
            self.content_x + 40, info_y - 20,
            self.content_width - 80, 80,
            color=(30, 30, 30)
        )
        info_bg.draw()

        info_border = shapes.Box(
            self.content_x + 40, info_y - 20,
            self.content_width - 80, 80,
            thickness=2, color=(50, 150, 255)
        )
        info_border.draw()

        info_text = pyglet.text.Label(
            'Click a keybind box and type the new key',
            font_size=14,
            x=self.content_x + 60,
            y=info_y + 30,
            anchor_x='left',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        info_text.draw()

        info_text2 = pyglet.text.Label(
            'Supported: letters (a-z), space, f1-f12, escape',
            font_size=11,
            x=self.content_x + 60,
            y=info_y + 10,
            anchor_x='left',
            anchor_y='center',
            color=(200, 200, 200, 255)
        )
        info_text2.draw()

    def _draw_serial_settings(self):
        """Draw serial settings tab"""
        col1_x = self.content_x + 40
        y = self.content_y + 30

        label = pyglet.text.Label(
            'Serial Port:',
            font_size=14,
            x=col1_x,
            y=y + 20,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        label.draw()
        self.serial_input.draw()

        # Platform examples
        info_y = y + 100
        example_bg = shapes.Rectangle(
            col1_x, info_y,
            self.content_width - 80, 140,
            color=(30, 30, 30)
        )
        example_bg.draw()

        example_border = shapes.Box(
            col1_x, info_y,
            self.content_width - 80, 140,
            thickness=2, color=(50, 150, 255)
        )
        example_border.draw()

        title_label = pyglet.text.Label(
            'Platform Examples:',
            font_size=14,
            x=col1_x + 20,
            y=info_y + 110,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 255, 255)
        )
        title_label.draw()

        examples = [
            'Windows:  COM3, COM4, COM5, ...',
            'Linux:    /dev/ttyUSB0, /dev/ttyACM0',
            'macOS:    /dev/cu.usbserial, /dev/cu.usbmodem'
        ]

        for i, example in enumerate(examples):
            ex_label = pyglet.text.Label(
                example,
                font_size=11,
                x=col1_x + 40,
                y=info_y + 70 - i * 25,
                anchor_x='left',
                anchor_y='center',
                color=(200, 200, 200, 255)
            )
            ex_label.draw()

        # Status info
        status_y = info_y - 70
        status_bg = shapes.Rectangle(
            col1_x, status_y,
            self.content_width - 80, 60,
            color=(30, 30, 30)
        )
        status_bg.draw()

        status_border = shapes.Box(
            col1_x, status_y,
            self.content_width - 80, 60,
            thickness=2, color=(255, 255, 50)
        )
        status_border.draw()

        status_text = pyglet.text.Label(
            'Note: Serial port changes require reconnection',
            font_size=14,
            x=col1_x + 20,
            y=status_y + 30,
            anchor_x='left',
            anchor_y='center',
            color=(255, 255, 50, 255)
        )
        status_text.draw()

    def handle_click(self, mx, my):
        """Handle mouse click - returns True if settings were saved"""
        if not self.active:
            return False

        # Color picker gets priority
        if self.color_picker.active:
            result = self.color_picker.handle_click(mx, my)
            if result == 'ok' and self.editing_color:
                self.color_swatches[self.editing_color].update_color(self.color_picker.color)
                self.editing_color = None
            elif result == 'cancel':
                self.editing_color = None
            return False

        # Tab switching
        for i, button in enumerate(self.tab_buttons):
            if button.contains(mx, my):
                self.tab = i
                return False

        # Save/Cancel buttons
        if self.save_button.contains(mx, my):
            self._save_settings()
            self.hide()
            return True

        if self.cancel_button.contains(mx, my):
            self.hide()
            return False

        # Tab-specific widgets
        if self.tab == 0:  # Display
            self.width_input.handle_click(mx, my)
            self.height_input.handle_click(mx, my)

        elif self.tab == 1:  # Colors
            for key, swatch in self.color_swatches.items():
                if swatch.contains(mx, my):
                    self.editing_color = key
                    self.color_picker.show(swatch.color)
                    break

        elif self.tab == 2:  # Keybinds
            for input_box in self.keybind_inputs.values():
                input_box.handle_click(mx, my)

        elif self.tab == 3:  # Serial
            self.serial_input.handle_click(mx, my)

        return False

    def handle_release(self):
        """Handle mouse release"""
        self.color_picker.handle_release()

    def handle_motion(self, mx, my):
        """Handle mouse motion"""
        if not self.active:
            return

        # Color picker
        if self.color_picker.active:
            self.color_picker.handle_motion(mx, my)
            return

        # Update hover states
        for button in self.tab_buttons:
            button.update_hover(mx, my)

        self.save_button.update_hover(mx, my)
        self.cancel_button.update_hover(mx, my)

        if self.tab == 1:
            for swatch in self.color_swatches.values():
                swatch.update_hover(mx, my)

    def handle_drag(self, mx, my):
        """Handle mouse drag"""
        if self.color_picker.active:
            self.color_picker.handle_motion(mx, my)

    def handle_text(self, text):
        """Handle text input"""
        if not self.active or self.color_picker.active:
            return

        if self.tab == 0:
            self.width_input.handle_text(text)
            self.height_input.handle_text(text)
        elif self.tab == 2:
            for input_box in self.keybind_inputs.values():
                input_box.handle_text(text)
        elif self.tab == 3:
            self.serial_input.handle_text(text)

    def handle_backspace(self):
        """Handle backspace"""
        if not self.active or self.color_picker.active:
            return

        if self.tab == 0:
            self.width_input.handle_backspace()
            self.height_input.handle_backspace()
        elif self.tab == 2:
            for input_box in self.keybind_inputs.values():
                input_box.handle_backspace()
        elif self.tab == 3:
            self.serial_input.handle_backspace()

    def _save_settings(self):
        """Save all settings to config"""
        # Display
        try:
            self.config.set(int(self.width_input.text), 'window_width')
            self.config.set(int(self.height_input.text), 'window_height')
        except ValueError:
            pass

        # Colors
        for name, swatch in self.color_swatches.items():
            self.config.set(swatch.color, 'colors', name)

        # Keybinds
        for name, input_box in self.keybind_inputs.items():
            self.config.set(input_box.text.lower(), 'keybinds', name)

        # Serial
        self.config.set(self.serial_input.text, 'serial_port')

        # Save to file
        self.config.save_config()


class CurveTracerApp:
    def __init__(self):
        self.config = ConfigManager()

        # Window setup
        self.width = self.config.get('window_width')
        self.height = self.config.get('window_height')
        self.window = pyglet.window.Window(
            width=self.width,
            height=self.height,
            caption="PyCurveBug - Pyglet Edition",
            resizable=True
        )

        # Load colors
        self._load_colors()

        # Serial connection
        self.serial = None
        self.connect()

        # Data storage
        self.ch1_std = []
        self.ch2_std = []
        self.ch1_voltage_std = []
        self.ch2_voltage_std = []
        self.drive_voltage_std = []

        self.ch1_weak = []
        self.ch2_weak = []
        self.ch1_voltage_weak = []
        self.ch2_voltage_weak = []
        self.drive_voltage_weak = []

        self.ch1 = []
        self.ch2 = []
        self.ch1_voltage = []
        self.ch2_voltage = []
        self.drive_voltage = []

        # State
        self.frame_count = 0
        self.paused = False
        self.single_channel = False
        self.auto_scale = False
        self.excitation_mode = 0
        self.alt_use_weak = False
        self.last_mode_was_weak = False

        # Pan/Zoom
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.dragging = False
        self.drag_start_pos = None
        self.drag_start_offset = None

        # Batch for efficient drawing
        self.batch = pyglet.graphics.Batch()
        self.shapes_list = []

        # Labels
        self.label_font_size = 12
        self.title_font_size = 16

        # Settings window
        self.settings_window = SettingsWindow(self.config, self.width, self.height)

        # Settings button
        self._create_settings_button()

        # Event handlers
        self.window.on_draw = self.on_draw
        self.window.on_key_press = self.on_key_press
        self.window.on_text = self.on_text
        self.window.on_mouse_press = self.on_mouse_press
        self.window.on_mouse_release = self.on_mouse_release
        self.window.on_mouse_drag = self.on_mouse_drag
        self.window.on_mouse_scroll = self.on_mouse_scroll
        self.window.on_mouse_motion = self.on_mouse_motion
        self.window.on_resize = self.on_resize

        # Schedule data acquisition
        pyglet.clock.schedule_interval(self.update, 1 / 20.0)

        debug_print("PyCurveBug initialized")
        debug_print("Controls: SPACE=mode P=pause S=single A=auto F=fit R=reset F1=settings Q=quit")

    def _create_settings_button(self):
        """Create settings button"""
        self.settings_button = Button(
            self.width - 120, self.height - 100,
            100, 35,
            'Settings',
            (50, 50, 50),
            (255, 255, 255)
        )

    def _load_colors(self):
        """Load colors from config"""
        colors = self.config.get('colors')
        self.bg_color = self._normalize_color(colors['background'])
        self.dut1_color = self._normalize_color(colors['dut1_trace'])
        self.dut2_color = self._normalize_color(colors['dut2_trace'])
        self.dut1_dimmed = self._normalize_color(colors['dut1_dimmed'])
        self.dut2_dimmed = self._normalize_color(colors['dut2_dimmed'])
        self.grid_bg_color = self._normalize_color(colors['grid_background'])
        self.grid_color = self._normalize_color(colors['grid'])
        self.crosshair_color = self._normalize_color(colors['crosshair'])
        self.label_color = self._normalize_color(colors['label'])
        self.axis_color = self._normalize_color(colors['axis_title'])
        self.border_color = self._normalize_color(colors['border'])

    @staticmethod
    def _normalize_color(color):
        """Convert [0-255] RGB to [0-1] RGBA for pyglet"""
        return color[0] / 255, color[1] / 255, color[2] / 255, 1.0

    @staticmethod
    def _color_to_255(color):
        """Convert normalized color back to 0-255"""
        return int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)

    def connect(self):
        """Connect to serial port"""
        try:
            port = self.config.get('serial_port')
            self.serial = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.1)
            self.serial.reset_input_buffer()
            debug_print(f"Connected to {port}")
            return True
        except Exception as e:
            debug_print(f"Connection failed: {e}")
            # Try auto-detect
            detected = self.auto_detect_port()
            if detected:
                try:
                    self.serial = serial.Serial(detected, 115200, timeout=1)
                    time.sleep(0.1)
                    self.serial.reset_input_buffer()
                    debug_print(f"Auto-connected to {detected}")
                    self.config.set(detected, 'serial_port')
                    self.config.save_config()
                    return True
                except:
                    pass
            return False

    @staticmethod
    def auto_detect_port():
        """Try to auto-detect CurveBug"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        for port in ports:
            try:
                test_serial = serial.Serial(port, 115200, timeout=1)
                time.sleep(0.1)
                test_serial.reset_input_buffer()
                test_serial.write(b'T')

                data = bytearray()
                start = time.time()
                while len(data) < 2016 and time.time() - start < 1.0:
                    if test_serial.in_waiting > 0:
                        data.extend(test_serial.read(min(test_serial.in_waiting, 2016 - len(data))))

                test_serial.close()

                if len(data) == 2016:
                    debug_print(f"Auto-detected on {port}")
                    return port
            except:
                continue
        return None

    def acquire(self):
        """Acquire data from CurveBug"""
        if self.serial is None or not self.serial.is_open:
            return False

        try:
            # Determine command
            if self.excitation_mode == 0:
                command = b'T'
                store_as_weak = False
            elif self.excitation_mode == 1:
                command = b'W'
                store_as_weak = True
            else:
                if self.alt_use_weak:
                    command = b'W'
                    store_as_weak = True
                else:
                    command = b'T'
                    store_as_weak = False
                self.alt_use_weak = not self.alt_use_weak

            self.serial.reset_input_buffer()
            self.serial.write(command)

            data = bytearray()
            start = time.time()
            while len(data) < 2016:
                if time.time() - start > 0.5:
                    break
                if self.serial.in_waiting > 0:
                    data.extend(self.serial.read(min(self.serial.in_waiting, 2016 - len(data))))

            if len(data) != 2016:
                return False

            # Parse data
            values = []
            for i in range(0, len(data), 2):
                val = struct.unpack('<H', data[i:i + 2])[0]
                values.append(val & 0x0FFF)

            if len(values) != 1008:
                return False

            drive_voltage = values[0::3]
            ch1_raw = values[1::3]
            ch2_raw = values[2::3]

            ch1_current = [drive_voltage[i] - ch1_raw[i] for i in range(len(drive_voltage))]
            ch2_current = [drive_voltage[i] - ch2_raw[i] for i in range(len(drive_voltage))]

            # Store data
            if store_as_weak:
                self.ch1_voltage_weak = ch1_raw
                self.ch2_voltage_weak = ch2_raw
                self.ch1_weak = ch1_current
                self.ch2_weak = ch2_current
                self.drive_voltage_weak = drive_voltage
                self.last_mode_was_weak = True
            else:
                self.ch1_voltage_std = ch1_raw
                self.ch2_voltage_std = ch2_raw
                self.ch1_std = ch1_current
                self.ch2_std = ch2_current
                self.drive_voltage_std = drive_voltage
                self.last_mode_was_weak = False

            # Set active data
            if store_as_weak:
                self.ch1_voltage = self.ch1_voltage_weak
                self.ch2_voltage = self.ch2_voltage_weak
                self.ch1 = self.ch1_weak
                self.ch2 = self.ch2_weak
                self.drive_voltage = self.drive_voltage_weak
            else:
                self.ch1_voltage = self.ch1_voltage_std
                self.ch2_voltage = self.ch2_voltage_std
                self.ch1 = self.ch1_std
                self.ch2 = self.ch2_std
                self.drive_voltage = self.drive_voltage_std

            return True

        except Exception as e:
            debug_print(f"Acquire error: {e}")
            return False

    def update(self, dt):
        """Update loop - called by pyglet scheduler"""
        if not self.paused and not self.settings_window.active:
            if self.acquire():
                self.frame_count += 1

        # Update settings window
        self.settings_window.update(dt)

    def on_draw(self):
        """Draw everything"""
        self.window.clear()
        pyglet.gl.glClearColor(*self.bg_color)

        if not self.settings_window.active:
            # Calculate plot area
            margin = min(150, self.width // 10)
            plot_rect = {
                'x': margin,
                'y': 100,
                'width': self.width - margin - 50,
                'height': self.height - 220
            }

            self.draw_plot(plot_rect)
            self.draw_info()
            self.settings_button.draw()

        # Draw settings window (full screen when active)
        self.settings_window.draw()

    def draw_plot(self, rect):
        """Draw the I-V curve plot"""
        x, y, w, h = rect['x'], rect['y'], rect['width'], rect['height']

        # Background
        bg = shapes.Rectangle(x, y, w, h, color=self._color_to_255(self.grid_bg_color))
        bg.draw()

        # Title
        title_text = "I-V Characteristics - Dual DUT Comparison"
        if self.auto_scale:
            title_text += " [AUTO-SCALE]"
        else:
            title_text += f" [FIXED] Zoom:{self.zoom_level:.2f}x"

        title_label = pyglet.text.Label(
            title_text,
            font_size=self.title_font_size,
            x=x + w // 2, y=y + h + 30,
            anchor_x='center', anchor_y='center',
            color=self._color_to_255(self.axis_color) + (255,)
        )
        title_label.draw()

        if not self.ch1 or not self.ch2:
            no_data = pyglet.text.Label(
                'No Data',
                font_size=self.title_font_size,
                x=x + w // 2, y=y + h // 2,
                anchor_x='center', anchor_y='center',
                color=(255, 255, 255, 255)
            )
            no_data.draw()
            return

        # Calculate scale
        if self.auto_scale:
            if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
                all_x = self.ch1_voltage_std + self.ch2_voltage_std + self.ch1_voltage_weak + self.ch2_voltage_weak
                all_y = self.ch1_std + self.ch2_std + self.ch1_weak + self.ch2_weak
            else:
                all_x = self.ch1_voltage + self.ch2_voltage
                all_y = self.ch1 + self.ch2

            x_min = list_min(all_x)
            x_max = list_max(all_x)
            y_min = list_min(all_y)
            y_max = list_max(all_y)

            x_margin = (x_max - x_min) * 0.1 if x_max > x_min else 100
            x_min -= x_margin
            x_max += x_margin

            y_margin = (y_max - y_min) * 0.1 if y_max > y_min else 100
            y_min -= y_margin
            y_max += y_margin

            if x_max == x_min:
                x_max = x_min + 1
            if y_max == y_min:
                y_max = y_min + 1
        else:
            # Fixed scale with zoom/pan
            base_x_min = 0
            base_x_max = ADC_MAX
            y_range = ADC_MAX - 700
            base_y_max = y_range / 8
            base_y_min = -y_range * 7 / 8

            x_range_visible = (base_x_max - base_x_min) / self.zoom_level
            y_range_visible = (base_y_max - base_y_min) / self.zoom_level

            x_center = (base_x_max + base_x_min) / 2 + self.pan_offset_x
            y_center = (base_y_max + base_y_min) / 2 + self.pan_offset_y

            x_min = x_center - x_range_visible / 2
            x_max = x_center + x_range_visible / 2
            y_min = y_center - y_range_visible / 2
            y_max = y_center + y_range_visible / 2

        # Grid
        grid_color_255 = self._color_to_255(self.grid_color)
        for i in range(11):
            gx = x + (i * w) // 10
            line = shapes.Line(gx, y, gx, y + h, color=grid_color_255)
            line.draw()

            gy = y + (i * h) // 10
            line = shapes.Line(x, gy, x + w, gy, color=grid_color_255)
            line.draw()

        # Crosshairs
        crosshair_color_255 = self._color_to_255(self.crosshair_color)
        zero_x_norm = (ADC_ORIGIN - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        zero_y_norm = (0 - y_min) / (y_max - y_min) if y_max != y_min else 0.5

        if 0 <= zero_x_norm <= 1:
            zero_x_pos = int(x + w - (zero_x_norm * w))
            pyglet.gl.glLineWidth(2)
            line = shapes.Line(zero_x_pos, y, zero_x_pos, y + h, color=crosshair_color_255)
            line.draw()
            pyglet.gl.glLineWidth(1)

        if 0 <= zero_y_norm <= 1:
            zero_y_pos = int(y + (zero_y_norm * h))

            pyglet.gl.glLineWidth(2)
            line = shapes.Line(x, zero_y_pos, x + w, zero_y_pos, color=crosshair_color_255)
            line.draw()
            pyglet.gl.glLineWidth(1)

        # Draw traces
        if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
            if self.last_mode_was_weak:
                self._draw_trace(self.ch1_voltage_std, self.ch1_std, self.dut1_dimmed, rect, x_min, x_max, y_min, y_max)
                if not self.single_channel:
                    self._draw_trace(self.ch2_voltage_std, self.ch2_std, self.dut2_dimmed, rect, x_min, x_max, y_min,
                                     y_max)
                self._draw_trace(self.ch1_voltage_weak, self.ch1_weak, self.dut1_color, rect, x_min, x_max, y_min,
                                 y_max)
                if not self.single_channel:
                    self._draw_trace(self.ch2_voltage_weak, self.ch2_weak, self.dut2_color, rect, x_min, x_max, y_min,
                                     y_max)
            else:
                self._draw_trace(self.ch1_voltage_weak, self.ch1_weak, self.dut1_dimmed, rect, x_min, x_max, y_min,
                                 y_max)
                if not self.single_channel:
                    self._draw_trace(self.ch2_voltage_weak, self.ch2_weak, self.dut2_dimmed, rect, x_min, x_max, y_min,
                                     y_max)
                self._draw_trace(self.ch1_voltage_std, self.ch1_std, self.dut1_color, rect, x_min, x_max, y_min, y_max)
                if not self.single_channel:
                    self._draw_trace(self.ch2_voltage_std, self.ch2_std, self.dut2_color, rect, x_min, x_max, y_min,
                                     y_max)
        else:
            self._draw_trace(self.ch1_voltage, self.ch1, self.dut1_color, rect, x_min, x_max, y_min, y_max)
            if not self.single_channel:
                self._draw_trace(self.ch2_voltage, self.ch2, self.dut2_color, rect, x_min, x_max, y_min, y_max)

        # Axis labels
        label_color_255 = self._color_to_255(self.label_color) + (255,)
        for i in [0, 5, 10]:
            x_val = x_min + (x_max - x_min) * (10 - i) / 10
            label_x = x + (i * w) // 10
            label = pyglet.text.Label(
                f"{int(x_val)}",
                font_size=self.label_font_size,
                x=label_x, y=y - 25,
                anchor_x='center', anchor_y='center',
                color=label_color_255
            )
            label.draw()

        for i in [0, 5, 10]:
            y_val = y_min + (y_max - y_min) * i / 10
            label_y = y + (i * h) // 10
            label = pyglet.text.Label(
                f"{int(y_val)}",
                font_size=self.label_font_size,
                x=x - 25, y=label_y,
                anchor_x='right', anchor_y='center',
                color=label_color_255
            )
            label.draw()

        # Axis titles
        axis_color_255 = self._color_to_255(self.axis_color) + (255,)
        x_title = pyglet.text.Label(
            "DUT Voltage",
            font_size=self.title_font_size,
            x=x + w // 2, y=y - 50,
            anchor_x='center', anchor_y='center',
            color=axis_color_255
        )
        x_title.draw()

        y_title = pyglet.text.Label(
            "Current",
            font_size=self.title_font_size,
            x=x - 80, y=y + h // 2,
            anchor_x='center', anchor_y='center',
            color=axis_color_255
        )
        y_title.draw()

        # Legend
        legend_x = x + 20
        legend_y = y + h - 40

        dut1_color_255 = self._color_to_255(self.dut1_color)

        pyglet.gl.glLineWidth(4)
        line = shapes.Line(legend_x, legend_y, legend_x + 40, legend_y, color=dut1_color_255)
        line.draw()
        pyglet.gl.glLineWidth(1)

        label = pyglet.text.Label(
            "DUT1 (CH1 - Black Lead)",
            font_size=self.label_font_size,
            x=legend_x + 50, y=legend_y,
            anchor_x='left', anchor_y='center',
            color=dut1_color_255 + (255,)
        )
        label.draw()

        if not self.single_channel:
            dut2_color_255 = self._color_to_255(self.dut2_color)
            pyglet.gl.glLineWidth(4)
            line = shapes.Line(legend_x, legend_y - 30, legend_x + 40, legend_y - 30, color=dut2_color_255)
            line.draw()
            pyglet.gl.glLineWidth(1)
            label = pyglet.text.Label(
                "DUT2 (CH2 - Red Lead)",
                font_size=self.label_font_size,
                x=legend_x + 50, y=legend_y - 30,
                anchor_x='left', anchor_y='center',
                color=dut2_color_255 + (255,)
            )
            label.draw()

        # Border
        border_color_255 = self._color_to_255(self.border_color)
        border = shapes.Box(x, y, w, h, thickness=2, color=border_color_255)
        border.draw()

        # Pause overlay
        if self.paused:
            pause_label = pyglet.text.Label(
                "PAUSED",
                font_size=48,
                x=x + w // 2, y=y + h // 2,
                anchor_x='center', anchor_y='center',
                color=(255, 255, 0, 255)
            )
            pause_label.draw()

    def _draw_trace(self, voltages, currents, color, rect, x_min, x_max, y_min, y_max):
        """Draw a single trace"""
        x, y, w, h = rect['x'], rect['y'], rect['width'], rect['height']

        if len(voltages) < 2:
            return

        color_255 = self._color_to_255(color)

        # Build points
        points = []
        for i in range(len(voltages)):
            x_norm = (voltages[i] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
            y_norm = (currents[i] - y_min) / (y_max - y_min) if y_max != y_min else 0.5

            px = int(x + w - (x_norm * w))
            py = int(y + (y_norm * h))
            points.append((px, py))

        # Draw line segments between consecutive points
        for i in range(len(points) - 1):
            line = shapes.Line(
                points[i][0], points[i][1],
                points[i + 1][0], points[i + 1][1],
                color=color_255
            )
            line.draw()

    def draw_info(self):
        """Draw info panel"""
        info_y = 50

        if self.ch1 and self.ch2:
            info_lines = [
                f"CH1: {list_min(self.ch1):.0f}-{list_max(self.ch1):.0f}  Mean: {int(list_mean(self.ch1))}  Pts: {len(self.ch1)}",
                f"CH2: {list_min(self.ch2):.0f}-{list_max(self.ch2):.0f}  Mean: {int(list_mean(self.ch2))}  Pts: {len(self.ch2)}",
            ]

            colors = [
                self._color_to_255(self.dut1_color) + (255,),
                self._color_to_255(self.dut2_color) + (255,),
            ]

            for i, (line, color) in enumerate(zip(info_lines, colors)):
                label = pyglet.text.Label(
                    line,
                    font_size=self.label_font_size,
                    x=20, y=info_y - i * 22,
                    anchor_x='left', anchor_y='center',
                    color=color
                )
                label.draw()

        # Status
        mode_names = ["4.7K(T)", "100K WEAK(W)", "ALT"]
        mode_str = mode_names[self.excitation_mode]

        if self.excitation_mode == 2 and len(self.ch1) > 0:
            if self.last_mode_was_weak:
                mode_str = "ALT[W-bright T-dim]"
            else:
                mode_str = "ALT[T-bright W-dim]"

        pause_str = " [PAUSED]" if self.paused else ""
        single_str = " [SINGLE]" if self.single_channel else ""
        scale_str = " [AUTO]" if self.auto_scale else " [FIXED]"

        status_text = f"Frame: {self.frame_count} | Mode: {mode_str}{pause_str}{single_str}{scale_str}"

        status_label = pyglet.text.Label(
            status_text,
            font_size=self.label_font_size,
            x=20, y=self.height - 20,
            anchor_x='left', anchor_y='center',
            color=(200, 200, 200, 255)
        )
        status_label.draw()

        # Controls
        controls = "SPACE=mode P=pause S=single A=auto F=fit R=reset F1=settings Q=quit | Drag=pan Wheel=zoom"
        controls_label = pyglet.text.Label(
            controls,
            font_size=self.label_font_size,
            x=20, y=self.height - 40,
            anchor_x='left', anchor_y='center',
            color=(150, 150, 150, 255)
        )
        controls_label.draw()

        # Connection status
        conn_status = "Connected" if (self.serial and self.serial.is_open) else "NOT CONNECTED"
        conn_color = (50, 255, 150, 255) if (self.serial and self.serial.is_open) else (255, 50, 50, 255)
        conn_label = pyglet.text.Label(
            f"Serial: {conn_status}",
            font_size=self.label_font_size,
            x=self.width - 20, y=self.height - 20,
            anchor_x='right', anchor_y='center',
            color=conn_color
        )
        conn_label.draw()

    def fit_to_window(self):
        """Calculate zoom and pan to show all data"""
        if not self.ch1 or not self.ch2:
            return

        if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
            all_x = self.ch1_voltage_std + self.ch2_voltage_std + self.ch1_voltage_weak + self.ch2_voltage_weak
            all_y = self.ch1_std + self.ch2_std + self.ch1_weak + self.ch2_weak
        else:
            all_x = self.ch1_voltage + self.ch2_voltage
            all_y = self.ch1 + self.ch2

        data_x_min = list_min(all_x)
        data_x_max = list_max(all_x)
        data_y_min = list_min(all_y)
        data_y_max = list_max(all_y)

        x_margin = (data_x_max - data_x_min) * 0.2
        y_margin = (data_y_max - data_y_min) * 0.2
        data_x_min -= x_margin
        data_x_max += x_margin
        data_y_min -= y_margin
        data_y_max += y_margin

        data_x_range = data_x_max - data_x_min
        data_y_range = data_y_max - data_y_min

        base_x_min = 0
        base_x_max = ADC_MAX
        y_range = ADC_MAX - 700
        base_y_max = y_range / 8
        base_y_min = -y_range * 7 / 8

        base_x_range = base_x_max - base_x_min
        base_y_range = base_y_max - base_y_min

        zoom_x = base_x_range / data_x_range if data_x_range > 0 else 1.0
        zoom_y = base_y_range / data_y_range if data_y_range > 0 else 1.0

        self.zoom_level = min(zoom_x, zoom_y)
        if self.zoom_level > 1.0:
            self.zoom_level = 1.0

        data_x_center = (data_x_min + data_x_max) / 2
        data_y_center = (data_y_min + data_y_max) / 2

        base_x_center = (base_x_min + base_x_max) / 2
        base_y_center = (base_y_min + base_y_max) / 2

        self.pan_offset_x = data_x_center - base_x_center
        self.pan_offset_y = data_y_center - base_y_center

    def reset_view(self):
        """Reset zoom and pan"""
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0

    def get_key_from_config(self, action):
        """Get key from config string"""
        key_str = self.config.get('keybinds', action)
        if not key_str:
            return None

        key_str = key_str.lower().strip()

        # Map special keys
        key_map = {
            'space': key.SPACE,
            'escape': key.ESCAPE,
            'esc': key.ESCAPE,
            'f1': key.F1,
            'f2': key.F2,
            'f3': key.F3,
            'f4': key.F4,
            'f5': key.F5,
            'f6': key.F6,
            'f7': key.F7,
            'f8': key.F8,
            'f9': key.F9,
            'f10': key.F10,
            'f11': key.F11,
            'f12': key.F12,
        }

        # Check if it's a special key
        if key_str in key_map:
            return key_map[key_str]

        # Check if it's a single letter
        elif len(key_str) == 1 and key_str.isalpha():
            return ord(key_str)

        # Invalid key
        else:
            debug_print(f"Warning: Invalid keybind '{key_str}' for action '{action}'")
            return None

    def on_key_press(self, symbol, modifiers):
        """Handle keyboard input"""
        # Settings window handles ESC when active
        if self.settings_window.active and symbol == key.ESCAPE:
            if not self.settings_window.color_picker.active:
                self.settings_window.hide()
                return
            else:
                self.settings_window.color_picker.color = self.settings_window.color_picker.original_color.copy()
                self.settings_window.color_picker.hide()
                self.settings_window.editing_color = None
                return

        # Handle backspace for input boxes
        if self.settings_window.active and symbol == key.BACKSPACE:
            self.settings_window.handle_backspace()
            return

        # Skip other keys if settings is active
        if self.settings_window.active:
            return

        # Normal key handling
        if symbol == self.get_key_from_config('quit') or symbol == key.ESCAPE:
            self.window.close()
        elif symbol == key.SPACE:
            self.excitation_mode = (self.excitation_mode + 1) % 3
            debug_print(f"Mode: {['4.7K', '100K WEAK', 'ALT'][self.excitation_mode]}")
        elif symbol == self.get_key_from_config('pause'):
            self.paused = not self.paused
        elif symbol == self.get_key_from_config('single_channel'):
            self.single_channel = not self.single_channel
        elif symbol == self.get_key_from_config('auto_scale'):
            self.auto_scale = not self.auto_scale
        elif symbol == self.get_key_from_config('fit_window'):
            if not self.auto_scale:
                self.fit_to_window()
        elif symbol == self.get_key_from_config('reset_view'):
            if not self.auto_scale:
                self.reset_view()
        elif symbol == self.get_key_from_config('settings'):
            self.settings_window.show()

    def on_text(self, text):
        """Handle text input"""
        if self.settings_window.active:
            self.settings_window.handle_text(text)

    def on_mouse_press(self, x, y, button, modifiers):
        """Handle mouse press"""
        # Settings window gets priority
        if self.settings_window.active:
            if self.settings_window.handle_click(x, y):
                # Settings were saved, reload colors
                self._load_colors()
            return

        # Settings button (only if settings not active)
        if self.settings_button.contains(x, y):
            self.settings_window.show()
            return

        # Normal interaction
        if button == mouse.LEFT and not self.auto_scale:
            self.dragging = True
            self.drag_start_pos = (x, y)
            self.drag_start_offset = (self.pan_offset_x, self.pan_offset_y)

    def on_mouse_release(self, x, y, button, modifiers):
        """Handle mouse release"""
        if self.settings_window.active:
            self.settings_window.handle_release()
            return

        if button == mouse.LEFT:
            self.dragging = False

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        """Handle mouse drag"""
        if self.settings_window.active:
            self.settings_window.handle_drag(x, y)
            return

        if self.dragging and not self.auto_scale:
            plot_width = self.width - 200
            plot_height = self.height - 200

            x_range_visible = ADC_MAX / self.zoom_level
            y_range_visible = (ADC_MAX - 700) / self.zoom_level

            x_offset_change = -dx * x_range_visible / plot_width
            y_offset_change = dy * y_range_visible / plot_height

            self.pan_offset_x = self.drag_start_offset[0] - x_offset_change
            self.pan_offset_y = self.drag_start_offset[1] - y_offset_change

            # Update drag start for continuous dragging
            self.drag_start_pos = (x, y)
            self.drag_start_offset = (self.pan_offset_x, self.pan_offset_y)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """Handle mouse scroll (zoom)"""
        if self.settings_window.active:
            return

        if not self.auto_scale:
            if scroll_y > 0:
                self.zoom_level *= 1.2
            else:
                self.zoom_level /= 1.2
                self.zoom_level = max(0.1, self.zoom_level)

    def on_mouse_motion(self, x, y, dx, dy):
        """Handle mouse motion"""
        if self.settings_window.active:
            self.settings_window.handle_motion(x, y)
        else:
            self.settings_button.update_hover(x, y)

    def on_resize(self, width, height):
        """Handle window resize"""
        self.width = width
        self.height = height
        self.settings_window.update_screen_size(width, height)
        self._create_settings_button()

    def run(self):
        """Start the application"""
        pyglet.app.run()

        # Cleanup
        if self.serial:
            self.serial.close()


if __name__ == "__main__":
    app = CurveTracerApp()
    app.run()