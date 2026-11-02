const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the blank line issue
const oldCode = `  }, [state.isSharing]);

    return createReturnValue(state, startScreenShare, stopScreenShare, toggleScreenShare, replaceTrack);
  };
}`;

const newCode = `  }, [state.isSharing]);

    return createReturnValue(state, startScreenShare, stopScreenShare, toggleScreenShare, replaceTrack);
  };
}`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - removed blank line');
} else {
  console.log('Old code not found');
}