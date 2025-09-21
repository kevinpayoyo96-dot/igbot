# stats.py
from storage import count_today, count_last_hour
print("Today follows:", count_today("follow"))
print("Today unfollows:", count_today("unfollow"))
print("Last hour follows:", count_last_hour("follow"))
print("Last hour unfollows:", count_last_hour("unfollow"))
