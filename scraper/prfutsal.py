import os
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

from requests.exceptions import RequestException, ConnectionError
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from base64 import b64encode
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from decouple import config

from flask import Flask
from flask_classful import FlaskView, route


CHECK_TEXT = "There are no available slots for your preferred date."

# TELEBOT_URL = config("TELEBOT_URL")
TELEBOT_URL = "http://telebot-srv:3000"

app = Flask(__name__)


class ActiveSG:
    def __init__(self) -> None:
        self.session = requests.session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"
            }
        )
        self._get_creds()

        self.slots = defaultdict(list)

    def _get_creds(self):
        """Get credentials from .env file"""

        self.id = config("ACTIVESG_ID")
        self.pwd = config("ACTIVESG_PWD")

    def signin(self):
        """Signin into activesg account"""
        # Retrieve public key and csrf
        r = self.session.get("https://members.myactivesg.com/auth")
        soup = BeautifulSoup(r.content, "html.parser")
        pubkey = soup.select_one("input[name=rsapublickey]")["value"]
        csrf = soup.select_one("input[name=_csrf]")["value"]
        cipher = PKCS1_v1_5.new(RSA.importKey(pubkey))

        payload = {
            "email": self.id,
            "ecpassword": b64encode(cipher.encrypt(self.pwd.encode("ascii"))),
            "_csrf": csrf,
        }
        r = self.session.post(
            "https://members.myactivesg.com/auth/signin", data=payload
        )

        if r.status_code != 200:
            raise RequestException("Sign in failed. Wrong password?")

    def renew_cookies(self):
        """Renew cookies as scraping might take awhile"""
        self.session.get("https://members.myactivesg.com/auth")

    def check_slots(self, activity_id, venue_id, date, time):
        """
        Checks if pasir ris futsal court has available slots
        """
        # TODO: change this to only send POST request if there is tickets available
        url = f"https://members.myactivesg.com/facilities/ajax/getTimeslots?activity_id={activity_id}&venue_id={venue_id}&date={date}&time_from={time}"
        print(url)
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }

        success = False
        attempts = 0

        while not success and attempts < 3:
            try:
                r = self.session.get(
                    url,
                    headers=headers,
                )
                success = True
            except ConnectionError:
                attempts += 1
                print("Retrying query after 2 seconds")
                time.sleep(2)

        if r.status_code == 200:
            soup = BeautifulSoup(
                r.content.decode("utf-8").replace("\\", "")[1:-1],
                "html.parser",
            )

            # print(soup)

            for tag in soup.select('input[type="checkbox"]'):
                # print(tag)
                if not tag.has_attr("disabled"):
                    value = tag["value"]
                    print(value)
                    _, _, _, start_time, end_time = value.split(";")
                    self.slots[date].append((start_time, end_time))
        else:
            print(f"Unsuccessful response, status {r.status_code}")

    def run(self):
        """Run the program"""

        # Futsal at PR Recre Center
        activity_id = 207
        venue_id = 540
        period = 14
        time = int(datetime.now().timestamp())

        for i in range(1, period + 1):
            checked_date = datetime.now() + timedelta(days=i)
            checked_date = checked_date.strftime("%Y-%m-%d")

        self.check_slots(
            activity_id=activity_id, venue_id=venue_id, date=checked_date, time=time
        )

    def scheduled_run(self):
        """Run background scheduler"""

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(self.run, "interval", seconds=10)
        sched.start()

    def test(self):
        """Use this when testing"""
        self.signin()

        self.check_slots("207", "540", "2022-02-28", "1645632000")
        print(self.slots)


class FlaskApp(FlaskView):
    route_prefix = "/api/"

    @route("ping", methods=["GET"])
    def ping():
        return "scraper is running"

    @route("webhook", methods=["POST"])
    def post(location, date, time, available, booking_url=""):
        url = os.path.join(TELEBOT_URL, "api/webhook")

        headers = {"Content-Type": "application/json"}

        if available:
            message = f"There are slots available for {location}!! \U0001F973"
        else:
            message = "No slots available \U0001F614"

        data = {
            "date": str(datetime.date.today),
            "location": location,
            "time": time,
            "message": message,
        }

        if len(booking_url) > 0:
            data["url"] = booking_url

        response = requests.post(url, data=json.dumps(data), headers=headers)
        print(response)
        return "", 201


if __name__ == "__main__":
    futsal = ActiveSG()
    futsal.test()

    FlaskApp.register(app)
    app.run()
