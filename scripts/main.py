import time
import os
import yaml
from datetime import datetime, timedelta
import random
import logging
from threading import Event
from selenium.common.exceptions import WebDriverException
from logging.handlers import RotatingFileHandler

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class VintedBotError(Exception):
    """Base exception for Vinted bot errors."""
    pass

class VintedLoginError(VintedBotError):
    """Raised when login fails."""
    pass

class PublishingError(VintedBotError):
    """Raised when publishing fails."""
    pass

class VintedBot:
    def __init__(self):
        self.stop_flag = Event()
        self.stats = BotStats()
        self.logger = self._setup_logging()
        # Load config once here if you like, or each time in run_bot()

    def _setup_logging(self):
        logger = logging.getLogger('vinted_bot')
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler('vinted_bot.log', maxBytes=1024*1024, backupCount=5)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def stop(self):
        """Stop the bot gracefully."""
        self.logger.info("[INFO] Stop signal received. Setting stop_flag.")
        self.stop_flag.set()

    def add_random_delay(self, base_seconds, variation_percent=20):
        """Add a randomized delay to avoid detection or appear more human-like."""
        variation = base_seconds * (variation_percent / 100)
        delay = base_seconds + random.uniform(-variation, variation)
        time.sleep(max(0, delay))

    def go_to_drafts(self, driver, log_callback):
        """Navigate to the user's Drafts page with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            if self.stop_flag.is_set():
                log_callback("[INFO] Stop flag detected. Exiting go_to_drafts.")
                return False
            try:
                log_callback("[INFO] Navigating to Drafts page...")
                driver.get("https://www.vinted.com/member/drafts")
                self.add_random_delay(3)
                return True
            except WebDriverException as e:
                if attempt == max_retries - 1:
                    raise VintedBotError(f"Failed to navigate to drafts: {str(e)}")
                log_callback(f"[WARN] Navigation attempt {attempt + 1} failed, retrying...")
                self.add_random_delay(5)
        return False

    def publish_draft(self, driver, log_callback):
        """Publish the first available draft with improved error handling."""
        try:
            if self.stop_flag.is_set():
                log_callback("[INFO] Stop flag detected. Exiting publish_draft.")
                return (None, False)
            publish_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Publish')]")
            publish_button.click()
            self.add_random_delay(5)
            
            listing_url = driver.current_url
            log_callback(f"[INFO] Published draft. Listing URL: {listing_url}")
            self.stats.successful_publishes += 1
            return (listing_url, True)
        except Exception as e:
            self.stats.failed_publishes += 1
            log_callback(f"[ERROR] Failed to publish draft: {e}")
            return (None, False)
        finally:
            self.stats.total_attempts += 1

    def is_listing_live(self, driver, listing_url, log_callback):
        """Check if a listing is live with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            if self.stop_flag.is_set():
                log_callback("[INFO] Stop flag detected. Exiting is_listing_live.")
                return False
            try:
                driver.get(listing_url)
                self.add_random_delay(2)

                # Refine this selector to match Vinted's actual "view count" element
                views_element = driver.find_element(By.XPATH, "//span[contains(@class, 'view-count')]")
                views_text = views_element.text.strip()

                if views_text.isdigit() and int(views_text) > 0:
                    log_callback(f"[INFO] Listing is live with {views_text} views.")
                    return True
                log_callback("[INFO] Listing not yet live (0 views).")
                return False
            except Exception as e:
                if attempt == max_retries - 1:
                    log_callback(f"[ERROR] Failed to check listing status: {str(e)}")
                    return False
                self.add_random_delay(5)
        return False

    def run_bot(self, start_time, interval, log_callback):
        """
        Orchestrates the Vinted bot operations.
        - start_time (str): e.g. "06:00"
        - interval (int): minutes to wait after go-live
        - log_callback (callable): function to log messages
        """
        config = self._load_config()

        # 1) Credentials from environment OR config
        username = os.environ.get("VINTED_USERNAME", config["login"]["username"])
        password = os.environ.get("VINTED_PASSWORD", config["login"]["password"])
        
        # 2) Additional intervals (like check_live_interval)
        check_live_interval = config["intervals"]["check_live_interval_seconds"]

        # 3) Convert start time to a datetime for today's date
        now = datetime.now()
        start_dt = datetime.strptime(start_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )
        if start_dt < now:
            # If start time already passed, schedule it for tomorrow
            start_dt += timedelta(days=1)

        while datetime.now() < start_dt:
            if self.stop_flag.is_set():
                log_callback("[INFO] Stop flag detected before start time. Exiting run_bot.")
                return
            remaining_seconds = (start_dt - datetime.now()).total_seconds()
            log_callback(f"[INFO] Waiting for start time... {remaining_seconds:.0f} seconds left.")
            time.sleep(10)

        log_callback(f"[INFO] Starting Vinted bot at {datetime.now()}...")
        driver = self._create_webdriver()
        try:
            # Step 1: Log in
            self._login_to_vinted(driver, username, password, log_callback)
            if self.stop_flag.is_set():
                log_callback("[INFO] Stop flag detected after login. Exiting run_bot.")
                return

            keep_publishing = True
            while keep_publishing:
                # Stop check
                if self.stop_flag.is_set():
                    log_callback("[INFO] Stop flag detected. Ending listing loop.")
                    break

                # Go to Drafts
                success_nav = self.go_to_drafts(driver, log_callback)
                if not success_nav:
                    log_callback("[INFO] Navigation to drafts failed. Stopping loop.")
                    break

                # Publish the first draft found
                listing_url, success_pub = self.publish_draft(driver, log_callback)
                if not success_pub or not listing_url:
                    log_callback("[INFO] No more drafts to publish or publishing failed. Stopping.")
                    keep_publishing = False
                    break

                # Wait for the listing to go live
                listing_is_live = False
                while not listing_is_live:
                    if self.stop_flag.is_set():
                        log_callback("[INFO] Stop flag detected while checking if listing is live.")
                        break

                    listing_is_live = self.is_listing_live(driver, listing_url, log_callback)
                    if not listing_is_live:
                        log_callback(f"[INFO] Checking again in {check_live_interval} seconds...")
                        time.sleep(check_live_interval)

                if self.stop_flag.is_set():
                    log_callback("[INFO] Stop flag detected after listing is confirmed live.")
                    break

                # Once it's live, wait the specified interval before publishing the next
                log_callback(f"[INFO] Listing went live! Waiting {interval} minutes before next draft.")
                for _ in range(interval * 60):
                    if self.stop_flag.is_set():
                        log_callback("[INFO] Stop flag detected during interval wait.")
                        break
                    time.sleep(1)

        except Exception as e:
            log_callback(f"[ERROR] An unexpected error occurred: {e}")
        finally:
            driver.quit()
            log_callback("[INFO] WebDriver closed.")
            log_callback("[INFO] Bot session ended.")

    def _load_config(self):
        """
        Load settings from config.yaml (similar to previous usage).
        """
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "config", "config.yaml"
        )
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _create_webdriver(self):
        """
        Create a Selenium WebDriver instance (Chrome).
        """
        chrome_options = Options()
        # Uncomment for headless mode:
        # chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_options)
        driver.implicitly_wait(10)  # seconds
        return driver

    def _login_to_vinted(self, driver, username, password, log_callback):
        """
        Log into Vinted using the provided credentials.
        """
        log_callback("[INFO] Navigating to Vinted login page...")
        driver.get("https://www.vinted.com/login")  # Adjust domain if needed

        time.sleep(2)
        log_callback("[INFO] Entering credentials...")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(5)  # Wait for any redirects
        log_callback("[INFO] Login attempt complete.")

class BotStats:
    def __init__(self):
        self.total_attempts = 0
        self.successful_publishes = 0
        self.failed_publishes = 0
        self.start_time = datetime.now()
        
    def get_success_rate(self):
        if self.total_attempts == 0:
            return 0
        return (self.successful_publishes / self.total_attempts) * 100

    def get_summary(self):
        return {
            "total_attempts": self.total_attempts,
            "successful_publishes": self.successful_publishes,
            "failed_publishes": self.failed_publishes,
            "success_rate": self.get_success_rate(),
            "running_time": str(datetime.now() - self.start_time)
        }