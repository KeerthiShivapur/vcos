const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the setState callback - move function outside component
const oldCode = `setState(computeNewState);

function computeNewState(prev) {
  return {
    ...prev,
    stream: newStream,
    tracks: {
      video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
      audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
    }
  };
}`;

const newCode = `setState(updateState);

function updateState(prev) {
  return Object.assign({}, prev, {
    stream: newStream,
    tracks: {
      video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
      audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
    }
  });
}`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - Object.assign in named function');
} else {
  console.log('Old code not found');
}