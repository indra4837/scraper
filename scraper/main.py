import os
import requests
import json
import datetime

from flask import Flask, request, Response
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from decouple import config

CHECK_TEXT = "Sorry. No tickets available at the moment."
HEADERS_BS4 = {
    "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"
}

# TELEBOT_URL = config("TELEBOT_URL")
TELEBOT_URL = "http://telebot-srv:3000"


def check_BVB():
    """
    Checks if Borussia Dortmund tickets are available and sends POST request
    """
    # TODO: change this to only send POST request if there is tickets available
    tickets_unavailable = {"Bundesliga": False, "UCL": False, "Cup": False}
    urls = {"Bundesliga": "https://www.eventimsports.de/ols/bvb/en/bundesliga/channel/shop/index",
        "UCL": "https://www.eventimsports.de/ols/bvb/en/champions-league/channel/shop/index",
        "Cup": "https://www.eventimsports.de/ols/bvb/en/3liga/channel/shop/index",}

    for competition, url in urls.items():
        r = requests.get(
            url,
            headers=HEADERS_BS4,
        )

        soup = BeautifulSoup(r.content, "html.parser")
        for p in soup.find_all("p"):
            if p.text.strip() == CHECK_TEXT:
                tickets_unavailable[competition] = True
                break

    # extract only available tickets
    available_tix = {k: not v for k, v in tickets_unavailable.items() if not v}

    # all competitions do not have any avail tickets
    if len(available_tix) == 0:
        post(competition="", ticket_url="", available=False)
    else:
        for comp, available in available_tix.items():
            if available:
                post(competition=comp, ticket_url=urls[comp], available=available)



sched = BackgroundScheduler(daemon=True)
sched.add_job(check_BVB, 'interval', hours=6)
sched.start()

app = Flask(__name__)

@app.route("/api/ping", methods=['GET'])
def ping():
    return "scraper is running"

@app.route("/api/webhook", methods=["POST"])
def post(competition, ticket_url, available):
    url = os.path.join(TELEBOT_URL, "api/webhook")

    headers = {"Content-Type": "application/json"}

    if available:
        message = f"There are BVB tickets available for {competition}!! \U0001F973"
    else:
        message = "No BVB tickets available \U0001F614"
        ticket_url = ""

    data = {
        "date": str(datetime.date.today),
        "competition": competition,
        "message": message,
        "url": ticket_url
    }

    response = requests.post(
        url, data=json.dumps(data), headers=headers
    )
    print(response)
    return "", 201