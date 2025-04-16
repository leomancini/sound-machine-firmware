#!/usr/bin/env python3
import os
import json

def get_color_from_manifest(tag_id, sounds_dir):
    """Read the manifest file for a given tag ID and return the color."""
    try:
        # Strip any leading/trailing whitespace from tag_id
        tag_id = tag_id.strip()
        
        manifest_path = os.path.join(sounds_dir, tag_id, "manifest.json")
        print(f"DEBUG: Looking for manifest at: {manifest_path}")
        
        if os.path.exists(manifest_path):
            print(f"DEBUG: Manifest file exists for tag {tag_id}")
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_content = f.read()
                print(f"DEBUG: Raw manifest content: {manifest_content}")
                # Try to clean the content
                manifest_content = manifest_content.strip()
                print(f"DEBUG: Cleaned manifest content: {manifest_content}")
                manifest = json.loads(manifest_content)
                if 'color' in manifest:
                    color = manifest['color']
                    print(f"DEBUG: Found color in manifest: {color}, type: {type(color)}")
                    
                    # Ensure color is in the correct format [r, g, b]
                    if isinstance(color, list) and len(color) == 3:
                        # Already in the correct format
                        print(f"DEBUG: Color is in correct format: {color}")
                        # Ensure all values are integers and within range
                        r = max(0, min(255, int(color[0])))
                        g = max(0, min(255, int(color[1])))
                        b = max(0, min(255, int(color[2])))
                        print(f"DEBUG: Returning color values: R={r}, G={g}, B={b}")
                        return [r, g, b]
        else:
            print(f"DEBUG: Manifest file does not exist at: {manifest_path}")
    except Exception as e:
        print(f"DEBUG: Error in get_color_from_manifest: {e}")
        import traceback
        traceback.print_exc()
    return None

if __name__ == "__main__":
    # Use the same path as the audio player
    sounds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds")
    print(f"DEBUG: Sounds directory set to: {sounds_dir}")
    
    # Test with the tag ID from the debug output
    tag_id = "0009466586"
    color = get_color_from_manifest(tag_id, sounds_dir)
    
    if color:
        print(f"Successfully found color for tag {tag_id}: {color}")
    else:
        print(f"Failed to find color for tag {tag_id}") 