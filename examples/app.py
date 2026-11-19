from flask import Flask, render_template_string

from flask_alpine import Alpine

app = Flask(__name__)
Alpine(app, plugins=["persist", "collapse"])

PAGE = """<!doctype html>
<title>flask-alpine demo</title>
<div x-data="{ count: $persist(0), open: false }">
  <button @click="count++">Clicked <span x-text="count"></span> times</button>
  <button @click="open = !open">Toggle</button>
  <p x-show="open" x-collapse>Works fully offline.</p>
</div>
{{ alpine_scripts() }}
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    app.run(debug=True)
