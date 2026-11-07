"""OBSERVABILITY: record what every pipeline run did, so problems can be found without guessing.

Each stage of each run writes one row to ops.pipeline_runs: which run, which stage, did it succeed,
how many rows came out, how long it took, and the error message if it failed.
Query it any time:  select * from ops.pipeline_runs order by started_at desc;
"""
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

DDL = """
    create table if not exists ops.pipeline_runs (
        run_id varchar, stage varchar, status varchar, rows_out bigint,
        started_at timestamp, ended_at timestamp, duration_s double, error varchar)
"""


class StageResult:
    rows = None      # a stage sets this to the number of rows it produced


class RunLogger:
    def __init__(self, con):
        self.con = con
        self.run_id = uuid.uuid4().hex[:8]
        con.execute("create schema if not exists ops")
        con.execute(DDL)

    @contextmanager
    def stage(self, name):
        """Use as:  with log.stage('ingest') as s:  ...  s.rows = 123"""
        result = StageResult()
        started, t0 = datetime.now(), time.perf_counter()
        status, error = "SUCCESS", None
        try:
            yield result
        except Exception as exc:
            status, error = "FAILED", f"{type(exc).__name__}: {exc}"
            raise                           # still stop the run: we only record the failure here
        finally:                            # runs whether the stage succeeded or failed
            seconds = round(time.perf_counter() - t0, 3)
            self.con.execute("insert into ops.pipeline_runs values (?,?,?,?,?,?,?,?)",
                             [self.run_id, name, status, result.rows, started, datetime.now(), seconds, error])
            rows = "-" if result.rows is None else result.rows
            print(f"  {name:12} {status:8} rows={rows}  {seconds}s")