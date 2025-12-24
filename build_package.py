import os
import zipfile
import xml.etree.ElementTree as ET

def get_addon_info():
    if not os.path.exists('addon.xml'):
        raise FileNotFoundError("addon.xml not found in current directory")
    tree = ET.parse('addon.xml')
    root = tree.getroot()
    return root.get('id'), root.get('version')

def zip_addon(addon_id, version):
    # Current directory is the root of the addon
    cwd = os.getcwd()
    folder_name = os.path.basename(cwd)
    
    # Output filename: foldername-version.zip
    zip_name = f"{folder_name}-{version}.zip"
    dist_dir = os.path.join(cwd, 'dist')
    
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)
        
    zip_path = os.path.join(dist_dir, zip_name)
    
    print(f"Building package for {addon_id} v{version}")
    print(f"Output: {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(cwd):
            # Exclude directories
            # .git is intentionally NOT excluded to match the previous request's requirement
            dirs[:] = [d for d in dirs if d not in ['dist', '.idea', '.vscode', '__pycache__']]
            
            for file in files:
                # Exclude specific files
                if file == os.path.basename(__file__): # Exclude this script
                    continue
                if file == '.gitignore':
                    continue
                if file == 'movie_t9_cache.json': # Explicitly requested exclusion
                    continue
                if file == 'skip_intro_data.json': # Explicitly requested exclusion
                    continue
                if file.endswith('.pyc') or file.endswith('.DS_Store'):
                    continue
                
                file_path = os.path.join(root, file)
                
                # Calculate archive name
                # We want the structure inside zip to be: folder_name/file
                rel_path = os.path.relpath(file_path, cwd)
                arcname = os.path.join(folder_name, rel_path)
                
                print(f"Adding: {rel_path}")
                zipf.write(file_path, arcname)
                
    print("Package creation completed successfully.")

if __name__ == "__main__":
    try:
        addon_id, version = get_addon_info()
        zip_addon(addon_id, version)
    except Exception as e:
        print(f"Error: {e}")
