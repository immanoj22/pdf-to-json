#!/bin/sh
# The trained reference parser (AnyStyle, MIT) from a portable Ruby, run locally. Set
# ANYSTYLE_HOME to the folder holding rb/ (see docs/tail_parser.md), then
#   BOOK_ANYSTYLE_CMD=/path/to/tools/anystyle.sh
: "${ANYSTYLE_HOME:?set ANYSTYLE_HOME to the folder that holds rb/}"
export PATH="$ANYSTYLE_HOME/rb/bin:$PATH" GEM_HOME="$ANYSTYLE_HOME/rb/share/rubygems" GEM_PATH="$ANYSTYLE_HOME/rb/share/rubygems"
exec ruby "$GEM_HOME/bin/anystyle" "$@"
