#!/usr/bin/env python3
"""
Traffic Simulator for AutoSRE Demo.
Deterministically simulates connection exhaustion up to ~98/100 connections.
Can run against live PostgreSQL or via HTTP against victim service.
"""

import argparse
import sys
import time
import threading
import logging
from typing import List, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("traffic_simulator")

# Global pool to hold connections open in idle-in-transaction state
_ACTIVE_CONNECTIONS: List[Any] = []
_STOP_EVENT = threading.Event()

def simulate_with_psycopg2(host: str, port: int, dbname: str, user: str, password: str, target: int = 98, duration: int = 300):
    """
    Opens connections directly to PostgreSQL and puts them into idle in transaction.
    """
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed; falling back to simulated connection gauge.")
        simulate_mock_traffic(target, duration)
        return

    logger.info(f"Targeting {target} PostgreSQL connections on {host}:{port}/{dbname}...")
    _STOP_EVENT.clear()
    
    conns = []
    try:
        for i in range(target):
            if _STOP_EVENT.is_set():
                break
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    dbname=dbname,
                    user=user,
                    password=password,
                    connect_timeout=3
                )
                conn.autocommit = False
                cur = conn.cursor()
                # Run query and leave transaction open (idle in transaction)
                cur.execute("SELECT 101 AS user_id, 'login_session' AS event, NOW() AS ts")
                conns.append((conn, cur))
                if (i + 1) % 10 == 0 or (i + 1) == target:
                    logger.info(f"Generated {i + 1}/{target} open connections (idle in transaction)")
            except Exception as e:
                logger.warning(f"Connection #{i+1} failed: {e}")
                break
            time.sleep(0.02)

        logger.info(f"Successfully saturated pool to {len(conns)} active/idle connections. Holding for {duration}s...")
        start_time = time.time()
        while time.time() - start_time < duration and not _STOP_EVENT.is_set():
            time.sleep(1)

    finally:
        logger.info(f"Cleaning up {len(conns)} simulated connections...")
        for conn, cur in conns:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass
        logger.info("Traffic simulation finished.")

def simulate_mock_traffic(target: int = 98, duration: int = 300):
    """Fallback simulation when running without live Postgres daemon."""
    logger.info(f"Simulating traffic ramp-up to {target}/100 connections...")
    for c in range(15, target + 1, 5):
        if _STOP_EVENT.is_set():
            break
        logger.info(f"Simulated connections: {c}/100")
        time.sleep(0.1)
    logger.info(f"Connection saturation reached: {target}/100 connections.")

def stop_simulation():
    _STOP_EVENT.set()

def main():
    parser = argparse.ArgumentParser(description="AutoSRE Traffic Simulator")
    parser.add_argument("--target", type=int, default=98, help="Target connection count (default: 98)")
    parser.add_argument("--host", type=str, default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--dbname", type=str, default="victim_db", help="Database name")
    parser.add_argument("--user", type=str, default="autosre", help="Database user")
    parser.add_argument("--password", type=str, default="autosre_password", help="Database password")
    parser.add_argument("--duration", type=int, default=300, help="Hold duration in seconds")
    parser.add_argument("--mock", action="store_true", help="Force mock traffic without connecting")

    args = parser.parse_args()

    if args.mock:
        simulate_mock_traffic(args.target, args.duration)
    else:
        simulate_with_psycopg2(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
            target=args.target,
            duration=args.duration
        )

if __name__ == "__main__":
    main()
