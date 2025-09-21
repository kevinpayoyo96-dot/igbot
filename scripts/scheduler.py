# scheduler.py
import schedule, time
from actions import search_and_follow, unfollow_due

def job_follow(kw, n): search_and_follow(kw, batch_limit=n)
def job_unfollow(n):   unfollow_due(batch_limit=n)

schedule.every().day.at("10:12").do(job_follow, "cars",   8)
schedule.every().day.at("12:47").do(job_follow, "crypto", 6)
schedule.every().day.at("15:18").do(job_follow, "fitness",6)
schedule.every().day.at("18:33").do(job_follow, "cars",   8)
schedule.every().day.at("20:05").do(job_unfollow, 20)

print("Scheduler running… Ctrl+C to stop.")
while True:
    schedule.run_pending()
    time.sleep(1)
