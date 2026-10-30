import { useState, useEffect } from 'react';
import './App.css';

// Define the data shape matching the backend
interface ApiResponse {
  message: string;
  timestamp: string;
}

function App() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    // Fetch data from the Node.js backend
    fetch('/api/hello')
      .then((res) => res.json())
      .then((data: ApiResponse) => {
        setData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching data:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ padding: '2rem', fontFamily: 'Arial' }}>
      <h1>React + Node + TypeScript Fullstack App</h1>

      {loading ? (
        <p>Loading data from server...</p>
      ) : (
        <div style={{ background: '#f4f4f4', padding: '1rem', borderRadius: '8px' }}>
          <h3>Server Response:</h3>
          <p><strong>Message:</strong> {data?.message}</p>
          <p><strong>Timestamp:</strong> {data?.timestamp}</p>
        </div>
      )}
    </div>
  );
}

export default App;
