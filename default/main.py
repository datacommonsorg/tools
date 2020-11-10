# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from flask import Flask, redirect

app = Flask(__name__)

@app.route("/")
def main():
    """Temporarly, redirect / to /covid19/"""
    return redirect('https://datcom-website.uc.r.appspot.com/dashboard/?dashboardId=covid19')

@app.route("/dashboard")
def dashboard():
    """Temporarly, redirect / to /covid19/"""
    return redirect('https://datcom-website.uc.r.appspot.com/dashboard/?dashboardId=covid19')

@app.route("/covid19")
def covid19():
    """Only /covid19/ is a service.
    If the user types in /covid19, redirect to /covid19/."""
    return redirect('https://datcom-website.uc.r.appspot.com/dashboard/?dashboardId=covid19')

@app.route("/socialWellness")
def socialWellness():
    return redirect('https://datcom-website.uc.r.appspot.com/dashboard/?dashboardId=socialWellness')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
