#!/usr/bin/env python3
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'rqa'))

def main():
    parser = argparse.ArgumentParser(description='RQA Tool')
    parser.add_argument('command', choices=['generate', 'setup'])
    args = parser.parse_args()
    print(f'RQA Tool - {args.command} ready')

if __name__ == '__main__':
    main()
