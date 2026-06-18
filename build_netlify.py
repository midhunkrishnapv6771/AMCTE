import os
import shutil

# Create dist directory
os.makedirs("dist", exist_ok=True)

# Read index.html template
template_path = os.path.join("Download_Modules", "templates", "index.html")
with open(template_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace Flask Jinja url_for tags with static relative paths
content = content.replace("{{ url_for('static', filename='style.css') }}", "style.css")
content = content.replace("{{ url_for('static', filename='app.js') }}", "app.js")

# Write index.html to dist
with open(os.path.join("dist", "index.html"), "w", encoding="utf-8") as f:
    f.write(content)

# Copy static assets to dist root
shutil.copy(os.path.join("Download_Modules", "static", "style.css"), os.path.join("dist", "style.css"))
shutil.copy(os.path.join("Download_Modules", "static", "app.js"), os.path.join("dist", "app.js"))

print("Static frontend built successfully in dist/ folder!")

