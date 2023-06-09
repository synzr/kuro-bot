from mastodon import Mastodon
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta
from random import choice
import logging
import yaml
import os

__dirname__ = os.path.realpath(os.path.dirname(__file__))
temporary_blocked_content = {}


def get_avaliable_content() -> dict[str, dict[str, any]]:
    content_directory_path = os.getenv(
        "CONTENT_DIR_PATH", os.path.join(__dirname__, "./content/")
    )
    avaliable_content = {}

    for filename in os.listdir(content_directory_path):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(content_directory_path, filename)) as f:
                metadata = yaml.safe_load(f)

                metadata["media_file"] = os.path.abspath(metadata["media_file"])
                if not os.path.exists(metadata["media_file"]): continue

                avaliable_content[os.path.splitext(filename)[0]] = metadata
    
    return avaliable_content


def get_non_blocked_content(avaliable_keys: list[str]) -> str:
    choosed_key = choice(avaliable_keys)

    if choosed_key in temporary_blocked_content and \
        temporary_blocked_content[choosed_key] > datetime.utcnow():
        try: return get_non_blocked_content(avaliable_keys)
        except RecursionError: temporary_blocked_content.clear()

    return choosed_key


def generate_status_text(content: dict) -> str:
    result = f"{content['media_description']}\n\n"

    if content.get('media_source_note'):
        result += f"Source note: {content['media_source_note']}\n"
    
    if content.get('media_source_url'):
        result += f"Source URL: {content['media_source_url']}"
    
    return result


def impl_post(bot: Mastodon) -> None:
    avaliable_content = get_avaliable_content()

    content_key = get_non_blocked_content(
        list(avaliable_content.keys())
    )
    content = avaliable_content[content_key]

    media = bot.media_post(
        content["media_file"],
        description=content["media_description"]
    )

    media_id = media["id"]
    logging.info(f"Uploaded {content_key} to the Mastodon instance (media id: {media_id}).")
    
    status = bot.status_post(
        generate_status_text(content),
        media_ids=[media_id],
        sensitive=content["media_content_warning_data"]["content_warning_is_enabled"],
        spoiler_text=content["media_content_warning_data"]["content_warning_note"]
    )
    logging.info(f"Posted the status with {content_key} (media id: {media_id}).")

    temporary_blocked_content[content_key] \
        = datetime.utcnow() + timedelta(hours=6)
    logging.info(f"Blocked the {content_key} for next 6 hours.")


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%d-%b-%y %H:%M:%S'
    )

    bot = Mastodon(
        access_token=os.getenv("MASTODON_ACCESS_TOKEN"),
        api_base_url=os.getenv("MASTODON_API_URL", "https://botsin.space")
    )

    scheduler = BlockingScheduler(timezone='UTC')

    scheduler.add_jobstore("sqlalchemy", url=os.getenv("SQLITE_URL", "sqlite:///jobs.sqlite3"))
    scheduler.add_job(impl_post, 'interval', [bot], hours=1)

    try: scheduler.start()
    except (KeyboardInterrupt, SystemExit): scheduler.shutdown()


if __name__ == "__main__":
    main()
