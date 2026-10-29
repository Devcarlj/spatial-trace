"""Local CLI: python cli.py index VIDEO CLIP_ID | query QUESTION."""
import argparse
from core.keyframer import process_video
from core.query_service import query_memory
from database import init_db

def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("video")
    index.add_argument("clip_id")
    query = commands.add_parser("query")
    query.add_argument("question")
    args = parser.parse_args()
    init_db()
    if args.command == "index":
        print(process_video(args.video, args.clip_id))
    else:
        print(query_memory(args.question).model_dump_json(indent=2))

if __name__ == "__main__":
    main()
