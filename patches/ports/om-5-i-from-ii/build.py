#!/usr/bin/env python3
"""OM-5 I donor-based experimental patch builder; see README.md here."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from om5i_donor_patch import main

if __name__ == '__main__':
    main()
