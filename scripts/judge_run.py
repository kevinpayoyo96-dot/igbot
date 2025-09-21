# judge_run.py
import argparse
from actions import with_session, follow_profile, search_and_follow
from storage import count_today, count_last_hour

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default="cars")
    parser.add_argument("batch", nargs="?", type=int, default=8)
    parser.add_argument("--user", help="follow this exact username first", default=None)
    args = parser.parse_args()

    if args.user:
        d = with_session()
        try:
            ok,msg = follow_profile(d, args.user)
            print(f"{'✓' if ok else '×'} follow {args.user}: {msg}")
        finally:
            try: d.quit()
            except: pass

    # then run the normal search-based batch
    search_and_follow(args.keyword, batch_limit=args.batch)
    print(f"Today follows: {count_today('follow')}, last-hour follows: {count_last_hour('follow')}")

if __name__ == "__main__":
    main()
