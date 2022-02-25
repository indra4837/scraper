from asyncio import format_helpers
import os
from tabnanny import check
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


class color:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0;0m"


class ActiveSG:
    def __init__(self) -> None:
        self.session = requests.session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"
            }
        )
        self.token_cr = config("TOKEN_CR")
        self._get_creds()

        self.slots = defaultdict(list)
        self.chat_id = set()
        self.get_user_chat()

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

        self.renew_cookies()

    def get_user_chat(self):
        """Get all user chat id"""

        print(f"https://api.telegram.org/bot{self.token_cr}/getUpdates")

        response = requests.get(
            f"https://api.telegram.org/bot{self.token_cr}/getUpdates"
        )

        for i in response.json()["result"]:
            self.chat_id.add(i["message"]["chat"]["id"])

    def update_user(self):
        """POST request to update user using Telegram Bot"""

        # 02-02-2022: [1000, 1200], 03-02-2022: [0900, 1100]
        # Date: [StartTime, StartTime]
        data = {}

        available = False

        # available timeslots will be in following format: 1000 1200 1800
        timeslots = ""

        for date, slots in self.slots.items():
            for start_time, _ in slots:
                available = True

                # only append space if there is another timeslot in the string
                if len(timeslots) == 0:
                    timeslots = timeslots + start_time
                else:
                    timeslots = timeslots + " " + start_time

            if available:
                data[date] = timeslots

            # reset available flag to false for next iteration
            available = False

            # reset timeslots for other dates
            timeslots = ""

        message = ""

        # formulate text message
        for date, time in data.items():
            # message is empty
            if len(message) == 0:
                message = message + f"{date}: {time}"
                continue
            message = message + "\n" + f"{date}: {time}"

        for id in self.chat_id:
            requests.post(
                f"https://api.telegram.org/bot{self.token_cr}/sendMessage",
                params={
                    "chat_id": str(id),
                    "text": f"{message}",
                },
            )

    def run(self):
        """Run the program"""

        self.signin()

        # Futsal at PR Recre Center
        activity_id = 207
        venue_id = 540
        period = 14
        time = int(datetime.now().timestamp())

        for i in range(1, period):
            checked_date = datetime.now() + timedelta(days=i)
            checked_date = checked_date.strftime("%Y-%m-%d")

            self.check_slots(activity_id, venue_id, str(checked_date), time)

        self.update_user()

    def scheduled_run(self):
        """Run background scheduler"""

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(self.run, "interval", seconds=10)
        sched.start()

    def test(self):
        """Use this when testing"""
        self.signin()

        self.check_slots(207, 540, "2022-03-10", 1645816142)
        # print(self.slots)
        self.run()


if __name__ == "__main__":
    futsal = ActiveSG()
    futsal.run()
