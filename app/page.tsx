"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import LoadingSpinner from "@/components/LoadingSpinner";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faExternalLinkAlt } from '@fortawesome/free-solid-svg-icons';

export default function Home() {
  const [response, setResponse] = useState<any>(null);
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [websocket, setWebSocket] = useState<WebSocket | null>(null);

  const handleSearch = async () => {
    setLoading(true);
    setResponse(null);

    // Establish WebSocket connection
    const ws = new WebSocket("ws://localhost:8000/ws/agent");
    setWebSocket(ws);

    ws.onopen = () => {
      console.log("WebSocket connection established");
      const taskMessage = {
        id: "1",
        web_name: "Test Task",
        ques: task,
        web: "https://www.google.com",
      };
      ws.send(JSON.stringify(taskMessage));
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log("Received from server:", message);
      setResponse(message);
      setLoading(false);
    };

    ws.onclose = () => {
      console.log("WebSocket connection closed");
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setLoading(false);
    };

    // Cleanup on component unmount
    return () => {
      ws.close();
    };
  };

  const handleCancel = () => {
    if (websocket) {
      websocket.close();
      setWebSocket(null);
      setLoading(false);
      setResponse({ status: 'cancelled', details: 'Request has been cancelled.' });
    }
  };

  const extractHostname = (url: string) => {
    try {
      const { hostname } = new URL(url);
      return "View source at " + hostname.slice(4);
    } catch (error) {
      console.error("Invalid URL:", url);
      return "";
    }
  };

  return (
    <main className="flex flex-col w-full items-center pt-8">
      <div className="w-[640px] flex flex-col gap-4 mb-12">
        <h1 className='text-3xl'>
          Healthcare Copilot
        </h1>
        <div className="flex flex-col gap-2">
          <Label className='text-lg font-medium'>Task</Label>
          <Input value={task} onChange={(e) => setTask(e.target.value)} />
        </div>
        <Button onClick={handleSearch}>
          Execute Task
        </Button>
        {(response && !loading) ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-row gap-2 items-center">
              <div className="border-1 border-b border-black w-full" />
              <Label className='text-xs font-bold '>RESULTS</Label>
              <div className="border-1 border-b border-black w-full" />
            </div>
            <div className="flex flex-col gap-2">
              {response.status === 'task_completed' && response.details ? (
                <div className="flex flex-row flex-wrap gap-2 p-4 bg-accent rounded-lg items-center">
                  <p>{response.details.message}</p>
                  <span>
                    <a href={response.details.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline flex items-center gap-2">
                      <span>{extractHostname(response.details.url)}</span>
                      <FontAwesomeIcon icon={faExternalLinkAlt} />
                    </a>
                  </span>
                </div>
              ) : (
                <div className="flex flex-row gap-2">
                  <div className="px-4 py-2 bg-accent rounded-lg w-full">
                    <p>{response.details}</p>
                  </div>
                  <Button onClick={handleCancel} variant="destructive">
                    Cancel
                  </Button>
                </div>

              )}
            </div>
          </div>
        ) : loading ? (
          <LoadingSpinner />
        ) : null}
      </div>
    </main>
  );
}
