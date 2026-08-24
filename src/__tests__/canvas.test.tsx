import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import Home from '../app/page';

describe('OiiOii.ai Canvas & Studio Frontend', () => {
  it('renders studio title and 7-agent pipeline banner', () => {
    render(<Home />);
    expect(screen.getByText(/OiiOii.ai Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Autonomous 7-Agent AI Animation Engine/i)).toBeInTheDocument();
    expect(screen.getByText(/Free-Tier Multi-Provider \(NVIDIA-Free\)/i)).toBeInTheDocument();
  });

  it('allows switching between Canvas, Agent Team, Models, and Styles tabs', () => {
    render(<Home />);
    
    // Switch to Agent Team tab
    const agentTab = screen.getByRole('button', { name: /Agent Team/i });
    fireEvent.click(agentTab);
    expect(screen.getByText(/The 7-Agent Animation Team/i)).toBeInTheDocument();
    expect(screen.getByText(/Scriptwriter/i)).toBeInTheDocument();
    expect(screen.getByText(/Director/i)).toBeInTheDocument();

    // Switch to Models tab
    const modelsTab = screen.getByRole('button', { name: /25\+ Free Models/i });
    fireEvent.click(modelsTab);
    expect(screen.getByText(/25\+ Free-Tier AI Model Registry/i)).toBeInTheDocument();
    expect(screen.getByText(/Video Models \(25\+\)/i)).toBeInTheDocument();

    // Switch to Styles tab
    const stylesTab = screen.getByRole('button', { name: /150\+ Styles/i });
    fireEvent.click(stylesTab);
    expect(screen.getByText(/150\+ Cinematic Visual Styles/i)).toBeInTheDocument();
  });

  it('renders storyboard panels and allows adding new panels', () => {
    render(<Home />);
    expect(screen.getByText(/Scene 1: The Rainy Rooftop/i)).toBeInTheDocument();
    
    const addBtn = screen.getByRole('button', { name: /Add Storyboard Panel/i });
    fireEvent.click(addBtn);
    expect(screen.getByText(/Scene 4: New Sequence/i)).toBeInTheDocument();
  });
});
