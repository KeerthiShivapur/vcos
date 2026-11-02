const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the return statement - remove type annotation
const oldCode = `    const returnValue: UseScreenShareReturn = {
      isSharing: state.isSharing,
      stream: state.stream,
      error: state.error,
      tracks: state.tracks,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
    return returnValue;
  };
}`;

const newCode = `    const returnValue = {
      isSharing: state.isSharing,
      stream: state.stream,
      error: state.error,
      tracks: state.tracks,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
    return returnValue;
  };
}`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - removed type annotation');
} else {
  console.log('Old code not found');
}