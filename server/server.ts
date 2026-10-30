import express, { Request, Response } from 'express';
import cors from 'cors';

const app = express();
const PORT = 5000;

app.use(cors());
app.use(express.json());

// Define an interface for type safety
interface MessageResponse {
    message: string;
    timestamp: string;
}

// Simple API endpoint
app.get('/api/hello', (req: Request, res: Response<MessageResponse>) => {
    res.json({
        message: "Hello from the Node.js TypeScript backend! Working perfect now",
        timestamp: new Date().toISOString()
    });
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});