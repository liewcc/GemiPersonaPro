import sys, os

workspace_dir = r"d:\AI\GemiPersonaPro"
san_path = os.path.join(workspace_dir, "pages", "02_Asset_Sanitizer.py")
gem_path = os.path.join(workspace_dir, "pages", "03_Gems_Bookmark.py")
out_path = os.path.join(workspace_dir, "pages", "02_Utilities.py")

with open(san_path, "r", encoding="utf-8") as f:
    san_content = f.read()

with open(gem_path, "r", encoding="utf-8") as f:
    gem_content = f.read()

# Replace the Page Config
san_content = san_content.replace('page_title="GemiPersona | ASSET SANITIZER"', 'page_title="GemiPersona | UTILITIES"')

gem_lines = gem_content.splitlines()
gem_main_start = -1
gem_main_end = -1
gem_imports = []
gem_globals = []

# Extract imports and global functions/variables from Gems Bookmark
for i, line in enumerate(gem_lines):
    if line.startswith("import ") or line.startswith("from "):
        gem_imports.append(line)
    elif "def main():" in line:
        gem_main_start = i
    elif 'if __name__ == "__main__":' in line:
        gem_main_end = i
        break
    elif gem_main_start == -1 and line.strip() and not line.startswith("import ") and not line.startswith("from "):
        if "st.set_page_config" not in line and "apply_premium_style" not in line and "import streamlit as st" not in line and "nest_asyncio.apply()" not in line and "asyncio.set_event_loop_policy" not in line and "sys.platform ==" not in line:
            gem_globals.append(line)

unique_gem_imports = []
for imp in gem_imports:
    # basic check
    base_module = imp.split()[1].split(".")[0] if "import" in imp else imp.split()[1]
    if base_module not in san_content:
        unique_gem_imports.append(imp)

gem_body_lines = gem_lines[gem_main_start+1:gem_main_end]

parts = san_content.split('# --- Main Panel ---')
san_head = parts[0]
san_tail = '# --- Main Panel ---\n' + parts[1]

san_tail_indented = '\n'.join(['    ' + line for line in san_tail.splitlines()])

final_content = unique_gem_imports + gem_globals + [san_head, 'tab_sanitizer, tab_bookmark = st.tabs(["Asset Sanitizer", "Gems Bookmark"])\n', 'with tab_sanitizer:'] + [san_tail_indented] + ['with tab_bookmark:'] + gem_body_lines

with open(out_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(final_content))

# Clean up old files
os.remove(san_path)
os.remove(gem_path)
print("Conversion successful.")
