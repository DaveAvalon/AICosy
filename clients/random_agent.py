"""Unbiased random action-schema sampler for exercising the public game protocol."""
import random
import sys
from clients.common import ClientError, action_from_descriptor, parser, print_result, run_agent


def main():
    args = parser(__doc__, player="random-player", model="random-v1").parse_args()
    rng = random.Random(args.seed)

    def choose(observation, _rules):
        return action_from_descriptor(rng.choice(observation["available_actions"]), rng)

    try:
        print_result(run_agent(args, choose, kind="random-script"))
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
