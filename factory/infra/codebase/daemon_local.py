import os

# Force local mode for this daemon instance
os.environ["EMBEDDING_MODE"] = "local"

# Now import the rest of the daemon logic
from daemon import main

if __name__ == "__main__":
    main()
