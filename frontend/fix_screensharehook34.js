const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the return statement - add explicit return type
const oldCode = `    return {
      isSharing: state.isSharing,
      stream: state.stream,
      error: state.error,
      tracks: state.tracks,
      startScreenShare,
      stopScreenShare,
      toggleScreenShare,
      replaceTrack,
    };
  };
}`;

const newCode = `    const returnValue: UseScreenShareReturn = {
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
  console.log('Fixed useScreenShare.ts - explicit return variable');
} else {
  console.log('Old code not found');
}