import React from 'react';

const SonicMapPage = () => {
  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingBottom: '2rem' }}>

      <h1 style={{ textAlign: 'center', margin: '1rem 0', fontSize: '2rem', fontWeight: 'bold' }}>Sonic-map</h1>
      <iframe
        src="http://localhost:5001/sonic-map/index-new.html"
        title="Sonic Map"
        style={{ border: 'none', width: '95vw', maxWidth: '1200px', height: '70vh', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.10)' }}
        allowFullScreen
      />
    </div>
  );
};

export default SonicMapPage;
