"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function Home() {
  const [response, setResponse] = useState<any>(null);
  const [provider, setProvider] = useState('');
  const [plan, setPlan] = useState('');
  const [drug, setDrug] = useState('');

  const handleSearch = async () => {
    try {
      const res = await fetch('/api/your-endpoint', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ provider, plan, drug }),
      });
      const data = await res.json();
      setResponse(data);
    } catch (error) {
      console.error('Error fetching data:', error);
      setResponse('An error occurred while fetching data.');
    }
  };

  return (
    <main className="flex flex-col w-full items-center pt-8">

      <div className="w-[550px] flex flex-col gap-4">
        <h1 className='text-3xl'>
          Get Prior Authorization Criteria
        </h1>
        <div className="flex flex-col gap-2">
          <Label className='text-lg font-medium'>Insurance Provider</Label>
          <Input value={provider} onChange={(e) => setProvider(e.target.value)} />
        </div>
        <div className="flex flex-col gap-2">
          <Label className='text-lg font-medium'>Insurance Plan</Label>
          <Input value={plan} onChange={(e) => setPlan(e.target.value)} />
        </div>
        <div className="flex flex-col gap-2">
          <Label className='text-lg font-medium'>Drug Name</Label>
          <Input value={drug} onChange={(e) => setDrug(e.target.value)} />
        </div>
        <Button onClick={handleSearch}>
          Search
        </Button>
        {response && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-row gap-2 items-center">
              <div className="border-1 border-b border-black w-full" />
              <Label className='text-xs font-bold '>RESULTS</Label>
              <div className="border-1 border-b border-black w-full" />
            </div>
            <div className="p-4 bg-accent rounded-lg">
              {Array.isArray(response) ? (
                response.map((item, index) => (
                  <div key={index} className="mb-4">
                    <p>{item.text}</p>
                    <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-blue-500 underline">
                      {item.link}
                    </a>
                  </div>
                ))
              ) : (
                <p>{response}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
