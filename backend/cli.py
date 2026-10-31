"""Local CLI: python cli.py index VIDEO CLIP_ID | query QUESTION [--clip ID] | clips."""
import argparse
import json

from core.keyframer import process_video
from core.query_service import query_memory
from database import get_clip, init_db, list_clips

def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("video")
    index.add_argument("clip_id")
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--clip", dest="clip_id", default=None,
                       help="Restrict the search to this clip (default: newest/all as before)")
    commands.add_parser("clips")
    args = parser.parse_args()
    init_db()
    if args.command == "index":
        frames = process_video(args.video, args.clip_id)
        clip = get_clip(args.clip_id) or {}
        print(json.dumps({"clip_id": args.clip_id, "status": clip.get("status"),
                          "indexed_frame_count": len(frames),
                          "failed_frame_count": clip.get("failed_frame_count", 0)}, indent=2))
    elif args.command == "clips":
        print(json.dumps(list_clips(), indent=2))
    else:
        print(query_memory(args.question, args.clip_id).model_dump_json(indent=2))

if __name__ == "__main__":
    main()
