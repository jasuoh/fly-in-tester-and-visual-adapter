"""Tests for the solution checker: valid logs pass, every violation fails."""

import unittest

from fly_in_tester.checker import check_solution
from fly_in_tester.mapfile import FlyMap, parse_map


def chain(
    drones: int = 1, mid: str = "", link: str = "", extra: str = ""
) -> FlyMap:
    """Return the map s - a - g (with optional metadata)."""
    return parse_map(
        f"nb_drones: {drones}\nstart_hub: s 0 0\nhub: a 1 0 {mid}\n"
        f"end_hub: g 2 0\n{extra}connection: s-a {link}\n"
        f"connection: a-g {link}\n"
    )


def restricted(drones: int = 1, link: str = "") -> FlyMap:
    """Return the map s - r(restricted) - g."""
    return parse_map(
        f"nb_drones: {drones}\nstart_hub: s 0 0\n"
        "hub: r 1 0 [zone=restricted]\nend_hub: g 2 0\n"
        f"connection: s-r {link}\nconnection: r-g {link}\n"
    )


class Base(unittest.TestCase):
    """Assertion helpers."""

    def valid(self, fly_map: FlyMap, log: list[str]) -> None:
        """Assert that ``log`` is a valid solution."""
        self.assertEqual(check_solution(fly_map, log).errors, [])

    def invalid(self, fly_map: FlyMap, log: list[str], fragment: str) -> None:
        """Assert that ``log`` is rejected with ``fragment`` in an error."""
        errors = check_solution(fly_map, log).errors
        self.assertTrue(errors, "the log was accepted")
        self.assertTrue(any(fragment in e for e in errors),
                        f"{fragment!r} not in {errors}")


class ValidSolutionTests(Base):
    """Correct solutions must be accepted."""

    def test_single_drone(self) -> None:
        """A drone walking along the chain."""
        self.valid(chain(), ["D0-a", "D0-g"])

    def test_ids_may_start_at_one(self) -> None:
        """Drone ids from D1 are fine."""
        result = check_solution(chain(2), ["D1-a", "D1-g D2-a", "D2-g"])
        self.assertEqual((result.errors, result.id_base), ([], 1))

    def test_leaving_frees_space_in_the_same_turn(self) -> None:
        """D1 enters a in the turn D0 leaves it."""
        self.valid(chain(2), ["D0-a", "D0-g D1-a", "D1-g"])

    def test_high_capacity_moves_together(self) -> None:
        """Zone and link capacity 2 allow two drones at once."""
        fly_map = chain(2, "[max_drones=2]", "[max_link_capacity=2]")
        self.valid(fly_map, ["D0-a D1-a", "D0-g D1-g"])

    def test_restricted_flight(self) -> None:
        """Departure, landing, then on."""
        self.valid(restricted(), ["D0-s-r", "D0-r", "D0-g"])

    def test_restricted_pipeline(self) -> None:
        """A follow-up drone may start once the link is free again."""
        self.valid(restricted(2), [
            "D0-s-r", "D0-r", "D0-g D1-s-r", "D1-r", "D1-g"])

    def test_landing_frees_the_link(self) -> None:
        """A drone may depart on the link another drone lands from."""
        self.valid(restricted(2), [
            "D0-s-r", "D0-r D1-s-r", "D0-g D1-r", "D1-g"])


class RuleViolationTests(Base):
    """Every rule of the subject is enforced."""

    def test_acts_twice(self) -> None:
        """A drone cannot move twice in one turn."""
        self.invalid(chain(), ["D0-a D0-g"], "acts twice")

    def test_zone_capacity(self) -> None:
        """Two drones in a zone with max_drones 1."""
        fly_map = chain(2, link="[max_link_capacity=2]")
        self.invalid(fly_map, ["D0-a D1-a", "D0-g D1-g"], "zone a holds 2")

    def test_link_capacity(self) -> None:
        """Two drones on a connection with capacity 1."""
        fly_map = chain(2, "[max_drones=2]")
        self.invalid(fly_map, ["D0-a D1-a", "D0-g D1-g"], "connection a-s")

    def test_restricted_needs_the_flight_form(self) -> None:
        """A restricted zone cannot be entered in one turn."""
        self.invalid(restricted(), ["D0-r", "D0-g"], "restricted")

    def test_flight_must_land_next_turn(self) -> None:
        """A drone in flight cannot do anything else."""
        self.invalid(restricted(), ["D0-s-r", "D0-g"], "must land")

    def test_flight_that_never_lands(self) -> None:
        """A missing landing is reported."""
        self.invalid(restricted(), ["D0-s-r"], "did not reach")

    def test_two_flights_depart_together(self) -> None:
        """Two departures on a connection with capacity 1."""
        self.invalid(restricted(2),
                     ["D0-s-r D1-s-r", "D0-r D1-r", "D0-g", "D1-g"],
                     "connection r-s")

    def test_connection_form_for_normal_zone(self) -> None:
        """Only restricted zones use D<id>-<from>-<to>."""
        self.invalid(chain(), ["D0-s-a", "D0-g"], "not restricted")

    def test_blocked_zone(self) -> None:
        """Blocked zones cannot be entered."""
        fly_map = chain(1, extra="hub: b 1 1 [zone=blocked]\n"
                                 "connection: s-b\n")
        self.invalid(fly_map, ["D0-b", "D0-a", "D0-g"], "blocked")

    def test_missing_connection(self) -> None:
        """A move needs a connection."""
        self.invalid(chain(), ["D0-g"], "no connection")

    def test_wrong_origin(self) -> None:
        """A drone can only leave the zone it is in."""
        self.invalid(restricted(), ["D0-a-r", "D0-r", "D0-g"], "is in s")

    def test_moves_after_delivery(self) -> None:
        """A delivered drone must stay put."""
        self.invalid(chain(), ["D0-a", "D0-g", "D0-a"],
                     "after being delivered")

    def test_not_everyone_arrives(self) -> None:
        """All drones must reach the end zone."""
        self.invalid(chain(), ["D0-a"], "did not reach g")

    def test_empty_turn(self) -> None:
        """A turn without movement is not allowed."""
        self.invalid(chain(), ["D0-a", "", "D0-g"], "empty line")

    def test_malformed_token(self) -> None:
        """Tokens must look like D<id>-<zone>."""
        self.invalid(chain(), ["D0-a", "X1-g"], "malformed token")

    def test_wrong_drone_ids(self) -> None:
        """Ids must be 0..n-1 or 1..n."""
        self.invalid(chain(2), ["D0-a", "D0-g D2-a", "D2-g"], "drone ids")

    def test_no_movements(self) -> None:
        """Output without movements is not a solution."""
        self.invalid(chain(), [], "no movements")

    def test_error_list_is_limited(self) -> None:
        """A hopeless log does not produce an endless error list."""
        errors = check_solution(chain(), ["D0-g"] * 200).errors
        self.assertLessEqual(len(errors), 30)


if __name__ == "__main__":
    unittest.main()
