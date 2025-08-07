import bpy
from bpy.types import Operator
from mathutils import Vector
import os
import numpy as np
from PIL import Image
import pyperclipimg as pci
import bpy_extras.view3d_utils

# Configuration constants
NODE_MARGIN = -50 #  -65 #-50 would be good as well, more padding
NODE_EXTRA_HEIGHT = 0

def compute_selected_bounds(context, margin):
    """Calculate the bounding box of selected nodes with margin."""
    ui_scale = context.preferences.system.ui_scale
    space = context.space_data
    node_tree = space.edit_tree
    
    if not node_tree:
        return Vector((0, 0)), Vector((0, 0))

    bmin = Vector((1e8, 1e8))
    bmax = Vector((-1e8, -1e8))
    
    for node in node_tree.nodes:
        if not node.select:
            continue
            
        # Account for node size and extra height
        vmin = Vector((
            node.location_absolute.x,
            node.location_absolute.y - node.height - NODE_EXTRA_HEIGHT
        )) * ui_scale
        
        vmax = Vector((
            node.location_absolute.x + node.width,
            node.location_absolute.y
        )) * ui_scale
        
        bmin.x = min(bmin.x, vmin.x)
        bmin.y = min(bmin.y, vmin.y)
        bmax.x = max(bmax.x, vmax.x)
        bmax.y = max(bmax.y, vmax.y)

    return (
        bmin - Vector((margin, margin)),
        bmax + Vector((margin, margin))
    )

def capture_node_area(context):
    """Capture the selected node area as an image."""
    # Find window region
    region = None
    for r in context.area.regions:
        if r.type == 'WINDOW':
            region = r
            break
    
    if not region:
        return None, "Node editor window region not found"

    # Compute bounds in view2d space
    bmin, bmax = compute_selected_bounds(context, NODE_MARGIN)

    # Take a full-region screenshot to temp file
    tmp = os.path.join(bpy.app.tempdir, "numpy_magic_full.png")
    override = context.copy()
    override["region"] = region
    
    with context.temp_override(**override):
        bpy.ops.screen.screenshot_area(filepath=tmp)

    # Open and crop the image
    im = Image.open(tmp)
    v2d = region.view2d

    x1, y1 = v2d.view_to_region(bmin.x, bmin.y, clip=True)
    x2, y2 = v2d.view_to_region(bmax.x, bmax.y, clip=True)

    # Flip Y coordinate for PIL (origin at top-left)
    y1t = im.height - y2
    y2t = im.height - y1

    crop = im.crop((int(x1), int(y1t), int(x2), int(y2t)))
    return crop, None

def capture_viewport_screenshot(context):
    """Capture the current viewport as an image."""
    # Find window region
    region = None
    for r in context.area.regions:
        if r.type == 'WINDOW':
            region = r
            break
    
    if not region:
        return None, "Viewport window region not found"

    # Check if there are selected objects
    selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
    if not selected_objects:
        return None, "No mesh objects selected"

    # Take a full-region screenshot to temp file
    tmp = os.path.join(bpy.app.tempdir, "viewport_screenshot.png")
    override = context.copy()
    override["region"] = region
    
    with context.temp_override(**override):
        bpy.ops.screen.screenshot_area(filepath=tmp)

    # Open the image
    im = Image.open(tmp)
    
    # Calculate bounding box of selected objects in screen space
    bmin = Vector((1e8, 1e8))
    bmax = Vector((-1e8, -1e8))
    
    for obj in selected_objects:
        # Get object bounds in world space
        if obj.bound_box:
            for corner in obj.bound_box:
                # Transform corner to world space
                world_corner = obj.matrix_world @ Vector(corner)
                # Project to screen space
                screen_coord = bpy_extras.view3d_utils.location_3d_to_region_2d(region, context.space_data.region_3d, world_corner)
                if screen_coord:
                    bmin.x = min(bmin.x, screen_coord.x)
                    bmin.y = min(bmin.y, screen_coord.y)
                    bmax.x = max(bmax.x, screen_coord.x)
                    bmax.y = max(bmax.y, screen_coord.y)
    
    # Add padding
    padding = 50  # pixels
    bmin -= Vector((padding, padding))
    bmax += Vector((padding, padding))
    
    # Clamp to image bounds
    bmin.x = max(0, bmin.x)
    bmin.y = max(0, bmin.y)
    bmax.x = min(im.width, bmax.x)
    bmax.y = min(im.height, bmax.y)
    
    # Flip Y coordinate for PIL (origin at top-left)
    y1 = im.height - bmax.y
    y2 = im.height - bmin.y
    
    # Crop the image
    crop = im.crop((int(bmin.x), int(y1), int(bmax.x), int(y2)))
    return crop, None

class NODE_OT_copy_to_clipboard(Operator):
    """Copy selected nodes to clipboard as an image."""
    
    bl_idname = "node.copy_to_clipboard"
    bl_label = "Copy selected nodes to clipboard as image"
    bl_description = "Copy selected node area to clipboard as image"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.space_data and 
            context.space_data.type == 'NODE_EDITOR' and
            pci is not None
        )

    def execute(self, context):
        crop, error = capture_node_area(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        # Copy image to clipboard
        try:
            pci.copy(crop)
            self.report({'INFO'}, "Image copied to clipboard")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy to clipboard: {str(e)}")
            return {'CANCELLED'}

class VIEW3D_OT_copy_viewport_to_clipboard(Operator):
    """Copy current viewport to clipboard as an image."""
    
    bl_idname = "view3d.copy_viewport_to_clipboard"
    bl_label = "Copy viewport to clipboard as image"
    bl_description = "Copy current viewport to clipboard as image"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            context.space_data and 
            context.space_data.type == 'VIEW_3D' and
            pci is not None
        )

    def execute(self, context):
        screenshot, error = capture_viewport_screenshot(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        # Copy image to clipboard
        try:
            pci.copy(screenshot)
            self.report({'INFO'}, "Viewport image copied to clipboard")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy to clipboard: {str(e)}")
            return {'CANCELLED'}

def register():
    bpy.utils.register_class(NODE_OT_copy_to_clipboard)
    bpy.utils.register_class(VIEW3D_OT_copy_viewport_to_clipboard)

def unregister():
    bpy.utils.unregister_class(VIEW3D_OT_copy_viewport_to_clipboard)
    bpy.utils.unregister_class(NODE_OT_copy_to_clipboard)