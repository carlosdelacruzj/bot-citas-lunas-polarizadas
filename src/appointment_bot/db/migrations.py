from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from psycopg import Connection

from appointment_bot.db.migration_steps.v14_to_v15 import v14_to_v15
from appointment_bot.db.migration_steps.v15_to_v16 import v15_to_v16
from appointment_bot.db.migration_steps.v16_to_v17 import v16_to_v17
from appointment_bot.db.migration_steps.v17_to_v18 import v17_to_v18
from appointment_bot.db.migration_steps.v18_to_v19 import v18_to_v19
from appointment_bot.db.migration_steps.v19_to_v20 import v19_to_v20
from appointment_bot.db.migration_steps.v20_to_v21 import v20_to_v21
from appointment_bot.db.migration_steps.v21_to_v22 import v21_to_v22
from appointment_bot.db.migration_steps.v22_to_v23 import v22_to_v23
from appointment_bot.db.migration_steps.v23_to_v24 import v23_to_v24
from appointment_bot.db.migration_steps.v24_to_v25 import v24_to_v25
from appointment_bot.db.migration_steps.v25_to_v26 import v25_to_v26
from appointment_bot.db.migration_steps.v26_to_v27 import v26_to_v27
from appointment_bot.db.migration_steps.v27_to_v28 import v27_to_v28
from appointment_bot.db.migration_steps.v28_to_v29 import v28_to_v29
from appointment_bot.db.migration_steps.v29_to_v30 import v29_to_v30
from appointment_bot.db.migration_steps.v30_to_v31 import v30_to_v31
from appointment_bot.db.migration_steps.v31_to_v32 import v31_to_v32
from appointment_bot.db.migration_steps.v32_to_v33 import v32_to_v33
from appointment_bot.db.migration_steps.v33_to_v34 import v33_to_v34
from appointment_bot.db.migration_steps.v34_to_v35 import v34_to_v35
from appointment_bot.db.migration_steps.v35_to_v36 import v35_to_v36
from appointment_bot.db.migration_steps.v36_to_v37 import v36_to_v37
from appointment_bot.db.migration_steps.v37_to_v38 import v37_to_v38
from appointment_bot.db.migration_steps.v38_to_v39 import v38_to_v39
from appointment_bot.db.migration_steps.v39_to_v40 import v39_to_v40
from appointment_bot.db.migration_steps.v40_to_v41 import v40_to_v41
from appointment_bot.db.migration_steps.v41_to_v42 import v41_to_v42
from appointment_bot.db.migration_steps.v42_to_v43 import v42_to_v43
from appointment_bot.db.migration_steps.v43_to_v44 import v43_to_v44
from appointment_bot.db.migration_steps.v44_to_v45 import v44_to_v45
from appointment_bot.db.migration_steps.v45_to_v46 import v45_to_v46
from appointment_bot.db.migration_steps.v46_to_v47 import v46_to_v47
from appointment_bot.db.migration_steps.v47_to_v48 import v47_to_v48
from appointment_bot.db.migration_steps.v48_to_v49 import v48_to_v49
from appointment_bot.db.migration_steps.v49_to_v50 import v49_to_v50
from appointment_bot.db.migration_steps.v50_to_v51 import v50_to_v51
from appointment_bot.db.migration_steps.v51_to_v52 import v51_to_v52
from appointment_bot.db.migration_steps.v52_to_v53 import v52_to_v53
from appointment_bot.db.migration_steps.v53_to_v54 import v53_to_v54
from appointment_bot.db.migration_steps.v54_to_v55 import v54_to_v55
from appointment_bot.db.migration_steps.v55_to_v56 import v55_to_v56
from appointment_bot.db.migration_steps.v56_to_v57 import v56_to_v57
from appointment_bot.db.migration_steps.v57_to_v58 import v57_to_v58
from appointment_bot.db.migration_steps.v58_to_v59 import v58_to_v59
from appointment_bot.db.migration_steps.v59_to_v60 import v59_to_v60
from appointment_bot.db.migration_steps.v60_to_v61 import v60_to_v61
from appointment_bot.db.migration_steps.v61_to_v62 import v61_to_v62
from appointment_bot.db.migration_steps.v62_to_v63 import v62_to_v63
from appointment_bot.db.migration_steps.v63_to_v64 import v63_to_v64
from appointment_bot.db.migration_steps.v64_to_v65 import v64_to_v65
from appointment_bot.db.migration_steps.v65_to_v66 import v65_to_v66
from appointment_bot.db.migration_steps.v66_to_v67 import v66_to_v67
from appointment_bot.db.migration_steps.v67_to_v68 import v67_to_v68
from appointment_bot.db.migration_steps.v68_to_v69 import v68_to_v69
from appointment_bot.db.migration_steps.v69_to_v70 import v69_to_v70
from appointment_bot.db.migration_steps.v70_to_v71 import v70_to_v71
from appointment_bot.db.migration_steps.v71_to_v72 import v71_to_v72
from appointment_bot.db.migration_steps.v72_to_v73 import v72_to_v73
from appointment_bot.db.migration_steps.v73_to_v74 import v73_to_v74
from appointment_bot.db.schema_definition import create_current_schema
from appointment_bot.db.schema_validation import validate_current_schema

SCHEMA_VERSION = 74
_MIGRATION_LOCK_ID = 1_047_296_811


@dataclass(frozen=True)
class MigrationStep:
    from_version: int
    to_version: int
    apply: Callable[[Connection], None]


MIGRATION_STEPS = (
    MigrationStep(14, 15, v14_to_v15),
    MigrationStep(15, 16, v15_to_v16),
    MigrationStep(16, 17, v16_to_v17),
    MigrationStep(17, 18, v17_to_v18),
    MigrationStep(18, 19, v18_to_v19),
    MigrationStep(19, 20, v19_to_v20),
    MigrationStep(20, 21, v20_to_v21),
    MigrationStep(21, 22, v21_to_v22),
    MigrationStep(22, 23, v22_to_v23),
    MigrationStep(23, 24, v23_to_v24),
    MigrationStep(24, 25, v24_to_v25),
    MigrationStep(25, 26, v25_to_v26),
    MigrationStep(26, 27, v26_to_v27),
    MigrationStep(27, 28, v27_to_v28),
    MigrationStep(28, 29, v28_to_v29),
    MigrationStep(29, 30, v29_to_v30),
    MigrationStep(30, 31, v30_to_v31),
    MigrationStep(31, 32, v31_to_v32),
    MigrationStep(32, 33, v32_to_v33),
    MigrationStep(33, 34, v33_to_v34),
    MigrationStep(34, 35, v34_to_v35),
    MigrationStep(35, 36, v35_to_v36),
    MigrationStep(36, 37, v36_to_v37),
    MigrationStep(37, 38, v37_to_v38),
    MigrationStep(38, 39, v38_to_v39),
    MigrationStep(39, 40, v39_to_v40),
    MigrationStep(40, 41, v40_to_v41),
    MigrationStep(41, 42, v41_to_v42),
    MigrationStep(42, 43, v42_to_v43),
    MigrationStep(43, 44, v43_to_v44),
    MigrationStep(44, 45, v44_to_v45),
    MigrationStep(45, 46, v45_to_v46),
    MigrationStep(46, 47, v46_to_v47),
    MigrationStep(47, 48, v47_to_v48),
    MigrationStep(48, 49, v48_to_v49),
    MigrationStep(49, 50, v49_to_v50),
    MigrationStep(50, 51, v50_to_v51),
    MigrationStep(51, 52, v51_to_v52),
    MigrationStep(52, 53, v52_to_v53),
    MigrationStep(53, 54, v53_to_v54),
    MigrationStep(54, 55, v54_to_v55),
    MigrationStep(55, 56, v55_to_v56),
    MigrationStep(56, 57, v56_to_v57),
    MigrationStep(57, 58, v57_to_v58),
    MigrationStep(58, 59, v58_to_v59),
    MigrationStep(59, 60, v59_to_v60),
    MigrationStep(60, 61, v60_to_v61),
    MigrationStep(61, 62, v61_to_v62),
    MigrationStep(62, 63, v62_to_v63),
    MigrationStep(63, 64, v63_to_v64),
    MigrationStep(64, 65, v64_to_v65),
    MigrationStep(65, 66, v65_to_v66),
    MigrationStep(66, 67, v66_to_v67),
    MigrationStep(67, 68, v67_to_v68),
    MigrationStep(68, 69, v68_to_v69),
    MigrationStep(69, 70, v69_to_v70),
    MigrationStep(70, 71, v70_to_v71),
    MigrationStep(71, 72, v71_to_v72),
    MigrationStep(72, 73, v72_to_v73),
    MigrationStep(73, 74, v73_to_v74),
)


def _validate_migration_steps() -> None:
    expected = 14
    for step in MIGRATION_STEPS:
        if step.from_version != expected or step.to_version != expected + 1:
            raise RuntimeError("Migration steps must be consecutive, unique and ordered from v14.")
        expected = step.to_version
    if expected != SCHEMA_VERSION:
        raise RuntimeError("Migration steps must end at the required schema version.")


_validate_migration_steps()


def migrate_database(connection: Connection) -> None:
    """Create the current schema or reject unsupported schema versions atomically."""
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id integer PRIMARY KEY CHECK (id = 1),
            version integer NOT NULL CHECK (version >= 0)
        )
        """
    )
    row = connection.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    if row is None:
        create_current_schema(connection)
        validate_current_schema(connection, SCHEMA_VERSION)
        connection.execute(
            "INSERT INTO schema_version (id, version) VALUES (1, %s)",
            (SCHEMA_VERSION,),
        )
        return

    current_version = int(row["version"])
    for step in MIGRATION_STEPS:
        if current_version == step.from_version:
            step.apply(connection)
            current_version = step.to_version
    if current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is unsupported; "
            f"this installation requires version {SCHEMA_VERSION}."
        )
    validate_current_schema(connection, SCHEMA_VERSION)
