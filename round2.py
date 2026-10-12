from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "message": "Smart EV Charging Platform",
        "status": "SUCCESS",
        "stations": [
            {
                "stationId": "ST101",
                "name": "City Charging Hub",
                "location": "Coimbatore",
                "availableChargers": 2
            }
        ]
    }), 200

@app.route("/api/stations")
def stations():
    return jsonify({
        "stationId": "ST101",
        "name": "City Charging Hub",
        "location": "Coimbatore",
        "availableChargers": 2
    }), 200

@app.route("/api/chargers/CH101/availability")
def availability():
    return jsonify({
        "chargerId": "CH101",
        "status": "AVAILABLE",
        "powerKW": 22
    }), 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)