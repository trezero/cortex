# Cortex UI - Knowledge Engine Web Interface

A modern React-based web interface for the Cortex Knowledge Engine MCP Server. Built with TypeScript, Vite, and Tailwind CSS.

## 🎨 UI Overview

Cortex UI provides a comprehensive dashboard for managing your AI's knowledge base:

![UI Architecture](https://via.placeholder.com/800x400?text=Cortex+UI+Architecture)

### Key Features

- **📊 MCP Dashboard**: Monitor and control the MCP server
- **⚙️ Settings Management**: Configure credentials and RAG strategies
- **🕷️ Web Crawling**: Crawl documentation sites and build knowledge base
- **📚 Knowledge Management**: Browse, search, and organize knowledge items
- **💬 Interactive Chat**: Test RAG queries with real-time responses
- **📈 Real-time Updates**: WebSocket-based live updates across the UI

## 🏗️ Architecture

### Technology Stack

- **React 18.3**: Modern React with hooks and functional components
- **TypeScript**: Full type safety and IntelliSense support
- **Vite**: Fast build tool and dev server
- **Tailwind CSS**: Utility-first styling
- **Framer Motion**: Smooth animations and transitions
- **Lucide Icons**: Beautiful and consistent iconography
- **React Router**: Client-side routing

### Project Structure

```
cortex-ui/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── ui/             # Base UI components (Button, Card, etc.)
│   │   ├── layouts/        # Layout components (Sidebar, Header)
│   │   └── animations/     # Animation components
│   ├── pages/              # Page components
│   │   ├── MCPPage.tsx     # MCP Dashboard
│   │   ├── Settings.tsx    # Settings page
│   │   ├── Crawl.tsx       # Web crawling interface
│   │   ├── KnowledgeBase.tsx # Knowledge management
│   │   └── Chat.tsx        # RAG chat interface
│   ├── services/           # API and service layers
│   │   ├── api.ts          # Base API configuration
│   │   ├── mcpService.ts   # MCP server communication
│   │   └── chatService.ts  # Chat/RAG service
│   ├── contexts/           # React contexts
│   │   └── ToastContext.tsx # Toast notifications
│   ├── hooks/              # Custom React hooks
│   │   └── useStaggeredEntrance.ts # Animation hook
│   ├── types/              # TypeScript type definitions
│   └── lib/                # Utility functions
├── public/                 # Static assets
└── test/                   # Test files
```

## 📄 Pages Documentation

### 1. MCP Dashboard (`/mcp`)

The central control panel for the MCP server.

**Components:**
- **Server Control Panel**: Start/stop server, view status, select transport mode
- **Server Logs Viewer**: Real-time log streaming with auto-scroll
- **Available Tools Table**: Dynamic tool discovery and documentation
- **MCP Test Panel**: Interactive tool testing interface

**Features:**
- Dual transport support (SSE/stdio)
- Real-time status polling (5-second intervals)
- WebSocket-based log streaming
- Copy-to-clipboard configuration
- Tool parameter validation

### 2. Settings (`/settings`)

Comprehensive configuration management.

**Sections:**
- **Credentials**: 
  - OpenAI API key (encrypted storage)
  - Supabase connection details
  - MCP server configuration
- **RAG Strategies**:
  - Contextual Embeddings toggle
  - Hybrid Search toggle
  - Agentic RAG (code extraction) toggle
  - Reranking toggle

**Features:**
- Secure credential storage with encryption
- Real-time validation
- Toast notifications for actions
- Default value management

### 3. Web Crawling (`/crawl`)

Interface for crawling documentation sites.

**Components:**
- **URL Input**: Smart URL validation
- **Crawl Options**: Max depth, concurrent sessions
- **Progress Monitoring**: Real-time crawl status
- **Results Summary**: Pages crawled, chunks stored

**Features:**
- Intelligent URL type detection
- Sitemap support
- Recursive crawling
- Batch processing

### 4. Knowledge Base (`/knowledge`)

Browse and manage your knowledge items.

**Components:**
- **Knowledge Grid**: Card-based knowledge display
- **Search/Filter**: Search by title, type, tags
- **Knowledge Details**: View full item details
- **Actions**: Delete, refresh, organize

**Features:**
- Pagination support
- Real-time updates via WebSocket
- Type-based filtering (technical/business)
- Metadata display

### 5. RAG Chat (`/chat`)

Interactive chat interface for testing RAG queries.

**Components:**
- **Chat Messages**: Threaded conversation view
- **Input Area**: Query input with source selection
- **Results Display**: Formatted RAG results
- **Source Selector**: Filter by knowledge source

**Features:**
- Real-time streaming responses
- Source attribution
- Markdown rendering
- Copy functionality

## 🧩 Component Library

### Base UI Components

#### Button
```tsx
<Button 
  variant="primary|secondary|ghost" 
  size="sm|md|lg"
  accentColor="blue|green|purple|orange|pink"
  onClick={handleClick}
>
  Click me
</Button>
```

#### Card
```tsx
<Card accentColor="blue" className="p-6">
  <h3>Card Title</h3>
  <p>Card content</p>
</Card>
```

#### LoadingSpinner
```tsx
<LoadingSpinner size="sm|md|lg" />
```

### Layout Components

#### Sidebar
- Collapsible navigation
- Active route highlighting
- Icon + text navigation items
- Responsive design

#### Header
- Dark mode toggle
- User menu
- Breadcrumb navigation

### Animation Components

#### PageTransition
Wraps pages with smooth fade/slide animations:
```tsx
<PageTransition>
  <YourPageContent />
</PageTransition>
```

## 🔌 Services

### mcpService
Handles all MCP server communication:
- `startServer()`: Start the MCP server
- `stopServer()`: Stop the MCP server
- `getStatus()`: Get current server status
- `streamLogs()`: WebSocket log streaming
- `getAvailableTools()`: Fetch MCP tools

### api
Base API configuration with:
- Automatic error handling
- Request/response interceptors
- Base URL configuration
- TypeScript generics

### chatService
RAG query interface:
- `sendMessage()`: Send RAG query
- `streamResponse()`: Stream responses
- `getSources()`: Get available sources

## 🎨 Styling

### Tailwind Configuration
- Custom color palette
- Dark mode support
- Custom animations
- Responsive breakpoints

### Theme Variables
```css
--primary: Blue accent colors
--secondary: Gray/neutral colors
--success: Green indicators
--warning: Orange indicators
--error: Red indicators
```

## 🚀 Development

### Setup
```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Run tests
npm test
```

### Environment Variables
```env
VITE_API_URL=http://localhost:8080
```

### Hot Module Replacement
Vite provides instant HMR for:
- React components
- CSS modules
- TypeScript files

## 🧪 Testing

### Unit Tests
- Component testing with React Testing Library
- Service mocking with MSW
- Hook testing with @testing-library/react-hooks

### Integration Tests
- Page-level testing
- API integration tests
- WebSocket testing

## 📦 Build & Deployment

### Docker Support
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 5173
CMD ["npm", "run", "preview"]
```

### Production Optimization
- Code splitting by route
- Lazy loading for pages
- Image optimization
- Bundle size analysis

## 🔧 Configuration Files

### vite.config.ts
- Path aliases
- Build optimization
- Development server config

### tsconfig.json
- Strict type checking
- Path mappings
- Compiler options

### tailwind.config.js
- Custom theme
- Plugin configuration
- Purge settings

## 🤝 Contributing

### Code Style
- ESLint configuration
- Prettier formatting
- TypeScript strict mode
- Component naming conventions

### Git Workflow
- Feature branches
- Conventional commits
- PR templates
- Code review process
