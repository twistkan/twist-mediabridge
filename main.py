from bridge.app import main

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from bridge.diagnostics import self_test
        self_test(sys.argv[2])
    else:
        main('Send to phone' if '--send-to-phone' in sys.argv else None)
