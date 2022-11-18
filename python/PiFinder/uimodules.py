#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module contains all the UI Module classes

"""
import datetime
import time
import os
import sqlite3
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageOps

import solver
from obj_types import OBJ_TYPES
from image_util import gamma_correct_low, subtract_background, red_image

RED = (0, 0, 255)


class UIModule:
    __title__ = "BASE"

    def __init__(self, display, camera_image, shared_state, command_queues):
        self.title = self.__title__
        self.switch_to = None
        self.display = display
        self.shared_state = shared_state
        self.camera_image = camera_image
        self.command_queues = command_queues
        self.screen = Image.new("RGB", (128, 128))
        self.draw = ImageDraw.Draw(self.screen)
        self.font_base = ImageFont.truetype(
            "/usr/share/fonts/truetype/Roboto_Mono/static/RobotoMono-Regular.ttf", 10
        )
        self.font_bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/Roboto_Mono/static/RobotoMono-Bold.ttf", 10
        )
        self.font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/Roboto_Mono/static/RobotoMono-Regular.ttf", 15
        )

    def active(self):
        """
        Called when a module becomes active
        i.e. foreground controlling display
        """
        pass

    def update(self):
        """
        Called to trigger UI Updates
        to be overloaded by subclases and shoud
        end up calling self.screen_update to
        to the actual screen draw
        retun the results of the screen_update to
        pass any signals back to main
        """
        return self.screen_update()

    def screen_update(self):
        """
        called to trigger UI updates
        takes self.screen adds title bar and
        writes to display
        """
        self.draw.rectangle([0, 0, 128, 16], fill=(0, 0, 0))
        self.draw.rounded_rectangle([0, 0, 128, 16], radius=6, fill=(0, 0, 128))
        self.draw.text((6, 1), self.title, font=self.font_bold, fill=(0, 0, 0))

        self.display.display(self.screen.convert(self.display.mode))

        # We can return a UIModule class name to force a switch here
        tmp_return = self.switch_to
        self.switch_to = None
        return tmp_return

    def key_number(self, number):
        pass

    def key_up(self):
        pass

    def key_down(self):
        pass

    def key_enter(self):
        pass

    def key_b(self):
        pass

    def key_c(self):
        pass

    def key_d(self):
        pass


class UILocate(UIModule):
    """
    Display pushto info
    """

    __title__ = "LOCATE"

    def __init__(self, *args):
        self.object_text = ["No Object Found"]
        self.__catalogs = {"N": "NGC", "I": " IC", "M": "Mes"}
        self.sf_utils = solver.Skyfield_utils()
        self.font_huge = ImageFont.truetype(
            "/usr/share/fonts/truetype/Roboto_Mono/static/RobotoMono-Bold.ttf", 35
        )
        super().__init__(*args)

    def key_enter(self):
        """
        When enter is pressed, set the
        target
        """
        self.switch_to = "UICatalog"

    def update_object_text(self):
        """
        Generates object text
        """
        if not self.target:
            self.object_text = ["No Object Found"]
            return

        self.object_text = []
        object_type = OBJ_TYPES.get(self.target["obj_type"], self.target["obj_type"])
        self.object_text.append(
            object_type + " " * (18 - len(object_type)) + self.target["const"]
        )

    def aim_degrees(self):
        """
        Returns degrees in
        az/alt from current position
        to target
        """
        solution = self.shared_state.solution()
        location = self.shared_state.location()
        dt = self.shared_state.datetime()
        if location and dt and solution:
            if solution["Alt"]:
                # We have position and time/date!
                self.sf_utils.set_location(
                    location["lat"],
                    location["lon"],
                    location["altitude"],
                )
                target_alt, target_az = self.sf_utils.radec_to_altaz(
                    self.target["ra"],
                    self.target["dec"],
                    dt,
                )

                return target_az - solution["Az"], target_alt - solution["Alt"]
        else:
            return None, None

    def update(self):
        # Clear Screen
        self.draw.rectangle([0, 0, 128, 128], fill=(0, 0, 0))

        self.target = self.shared_state.target()
        if not self.target:
            self.draw.text((0, 20), "No Target Set", font=self.font_large, fill=RED)
            return self.screen_update()

        self.update_object_text()
        # Target Name
        line = self.__catalogs.get(self.target["catalog"], "UNK") + " "
        line += str(self.target["designation"])
        self.draw.text((0, 20), line, font=self.font_large, fill=RED)

        # ID Line in BOld
        self.draw.text((0, 40), self.object_text[0], font=self.font_bold, fill=RED)

        # Pointing Instructions
        point_az, point_alt = self.aim_degrees()
        if not point_az:
            self.draw.text((0, 50), " ---.-", font=self.font_huge, fill=RED)
            self.draw.text((0, 84), "  --.-", font=self.font_huge, fill=RED)
        else:
            if point_az >= 0:
                self.draw.text((0, 50), "+", font=self.font_huge, fill=RED)
            else:
                point_az *= -1
                self.draw.text((0, 50), "-", font=self.font_huge, fill=RED)
            self.draw.text(
                (25, 50), f"{point_az : >5.1f}", font=self.font_huge, fill=RED
            )

            if point_alt >= 0:
                self.draw.text((0, 84), "+", font=self.font_huge, fill=RED)
            else:
                point_alt *= -1
                self.draw.text((0, 84), "-", font=self.font_huge, fill=RED)
            self.draw.text(
                (25, 84), f"{point_alt : >5.1f}", font=self.font_huge, fill=RED
            )

        return self.screen_update()


class UICatalog(UIModule):
    """
    Search catalogs for object to find
    """

    __title__ = "CATALOG"

    def __init__(self, *args):
        self.__catalogs = ["NGC", " IC", "Mes"]
        self.catalog_index = 0
        self.designator = ["-"] * 4
        self.cat_object = None
        self.object_text = ["No Object Found"]
        root_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        db_path = os.path.join(root_dir, "astro_data", "pifinder_objects.db")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.db_c = self.conn.cursor()
        super().__init__(*args)

    def update_object_text(self):
        """
        Generates object text
        """
        if not self.cat_object:
            self.object_text = ["No Object Found"]
            return

        self.object_text = []
        object_type = OBJ_TYPES.get(
            self.cat_object["obj_type"], self.cat_object["obj_type"]
        )
        self.object_text.append(
            object_type + " " * (18 - len(object_type)) + self.cat_object["const"]
        )
        self.object_text.append("This is line Two")

    def update(self):
        # Clear Screen
        self.draw.rectangle([0, 0, 128, 128], fill=(0, 0, 0))

        # catalog and entry field
        line = self.__catalogs[self.catalog_index] + " "
        line += "".join(self.designator)
        self.draw.text((0, 25), line, font=self.font_large, fill=RED)

        # ID Line in BOld
        self.draw.text((0, 50), self.object_text[0], font=self.font_bold, fill=RED)

        # Remaining lines
        for i, line in enumerate(self.object_text[1:]):
            self.draw.text((0, i * 10 + 60), line, font=self.font_base, fill=RED)
        return self.screen_update()

    def key_d(self):
        self.catalog_index += 1
        if self.catalog_index >= len(self.__catalogs):
            self.catalog_index = 0
        if self.catalog_index == 2:
            # messier
            self.designator = ["-"] * 3
        else:
            self.designator = ["-"] * 4
        self.cat_object = None
        self.update_object_text()

    def key_number(self, number):
        self.designator = self.designator[1:]
        self.designator.append(str(number))
        if self.designator[0] in ["0", "-"]:
            index = 0
            go = True
            while go:
                self.designator[index] = "-"
                index += 1
                if index >= len(self.designator) or self.designator[index] not in [
                    "0",
                    "-",
                ]:
                    go = False
        # Check for match
        designator = "".join(self.designator).replace("-", "")
        catalog = self.__catalogs[self.catalog_index].strip()[0]
        self.cat_object = self.conn.execute(
            f"""
            SELECT * from objects
            where catalog = "{catalog}"
            and designation = "{designator}"
        """
        ).fetchone()
        self.update_object_text()

    def key_enter(self):
        """
        When enter is pressed, set the
        target
        """
        if self.cat_object:
            self.shared_state.set_target(dict(self.cat_object))
            self.switch_to = "UILocate"

    def scroll_obj(self, direction):
        """
        Looks for the next object up/down
        sets the designation and object
        """
        if direction == "<":
            sort_order = "desc"
        else:
            sort_order = ""

        designator = "".join(self.designator).replace("-", "")
        catalog = self.__catalogs[self.catalog_index].strip()[0]

        tmp_obj = self.conn.execute(
            f"""
            SELECT * from objects
            where catalog = "{catalog}"
            and designation {direction} "{designator}"
            order by designation {sort_order}
        """
        ).fetchone()

        if tmp_obj:
            self.cat_object = tmp_obj
            desig = str(tmp_obj["designation"])
            desig = list(desig)
            if self.catalog_index == 2:
                desig = ["-"] * (3 - len(desig)) + desig
            else:
                desig = ["-"] * (4 - len(desig)) + desig

            self.designator = desig
            self.update_object_text()

    def key_up(self):
        self.scroll_obj("<")

    def key_down(self):
        self.scroll_obj(">")


class UIStatus(UIModule):
    """
    Displays various status information
    """

    __title__ = "STATUS"

    def __init__(self, *args):
        self.status_dict = {
            "LST SLV": "--",
            "RA": "--",
            "DEC": "--",
            "AZ": "--",
            "ALT": "--",
            "GPS": "--",
            "UTC DT": "--",
            "UTC TM": "--",
        }
        super().__init__(*args)

    def update_status_dict(self):
        """
        Updates all the
        status dict values
        """
        if self.shared_state.solve_state():
            solution = self.shared_state.solution()
            # last solve time
            self.status_dict["LST SLV"] = str(
                round(time.time() - solution["solve_time"])
            )

            self.status_dict["RA"] = str(round(solution["RA"], 3))
            self.status_dict["DEC"] = str(round(solution["Dec"], 3))

            if solution["Az"]:
                self.status_dict["ALT"] = str(round(solution["Alt"], 3))
                self.status_dict["AZ"] = str(round(solution["Az"], 3))

        location = self.shared_state.location()
        if location["gps_lock"]:
            self.status_dict["GPS"] = "LOCK"

        dt = self.shared_state.datetime()
        if dt:
            self.status_dict["UTC DT"] = dt.date().isoformat()
            self.status_dict["UTC TM"] = dt.time().isoformat()

    def update(self):
        self.update_status_dict()
        self.draw.rectangle([0, 0, 128, 128], fill=(0, 0, 0))
        lines = []
        for k, v in self.status_dict.items():
            line = " " * (7 - len(k)) + k
            line += ":"
            line += " " * (10 - len(v))
            line += v
            lines.append(line)

        for i, line in enumerate(lines):
            self.draw.text((0, i * 10 + 20), line, font=self.font_base, fill=RED)
        return self.screen_update()


class UIConsole(UIModule):
    __title__ = "CONSOLE"

    def __init__(self, *args):
        self.dirty = True
        self.lines = ["---- TOP ---"]
        self.scroll_offset = 0
        self.debug_mode = False
        super().__init__(*args)

    def set_shared_state(self, shared_state):
        self.shared_state = shared_state

    def key_number(self, number):
        if number == 0:
            self.command_queues["camera"].put("debug")
            if self.debug_mode:
                self.debug_mode = False
            else:
                self.debug_mode = True
            self.command_queues["console"].put("Debug: " + str(self.debug_mode))
        dt = datetime.datetime(2022, 11, 15, 2, 0, 0)
        self.shared_state.set_datetime(dt)

    def key_enter(self):
        # reset scroll offset
        self.scroll_offset = 0
        self.dirty = True

    def key_up(self):
        self.scroll_offset += 1
        self.dirty = True

    def key_down(self):
        self.scroll_offset -= 1
        if self.scroll_offset < 0:
            self.scroll_offset = 0
        self.dirty = True

    def write(self, line):
        """
        Writes a new line to the console.
        """
        print(f"Write: {line}")
        self.lines.append(line)
        # reset scroll offset
        self.scroll_offset = 0
        self.dirty = True

    def active(self):
        self.dirty = True
        self.update()

    def update(self):
        # display an image
        if self.dirty:
            # clear screen
            self.draw.rectangle([0, 0, 128, 128], fill=(0, 0, 0))
            for i, line in enumerate(self.lines[-10 - self.scroll_offset :][:10]):
                self.draw.text((0, i * 10 + 20), line, font=self.font_base, fill=RED)
            self.dirty = False
            return self.screen_update()


class UIPreview(UIModule):
    __title__ = "PREVIEW"

    def __init__(self, *args):
        self.last_image_update = time.time()
        super().__init__(*args)

    def update(self):
        # display an image
        last_image_time = self.shared_state.last_image_time()
        if last_image_time > self.last_image_update:
            image_obj = self.camera_image.copy()
            image_obj = image_obj.resize((128, 128), Image.LANCZOS)
            image_obj = subtract_background(image_obj)
            image_obj = image_obj.convert("RGB")
            image_obj = ImageChops.multiply(image_obj, red_image)
            image_obj = ImageOps.autocontrast(image_obj)
            image_obj = Image.eval(image_obj, gamma_correct_low)
            self.screen.paste(image_obj)
            last_image_fetched = last_image_time

            if self.shared_state.solve_state():
                solution = self.shared_state.solution()
                self.title = "PREVIEW - " + solution["constellation"]
            return self.screen_update()

    def key_up(self):
        self.command_queues["camera"].put("exp_up")

    def key_down(self):
        self.command_queues["camera"].put("exp_dn")

    def key_enter(self):
        self.command_queues["camera"].put("exp_save")
