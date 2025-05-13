import { ApplicationConfig, importProvidersFrom  } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideAnimations } from '@angular/platform-browser/animations';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import { FormsModule } from '@angular/forms';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideAnimations(),
    importProvidersFrom(MonacoEditorModule.forRoot({
      baseUrl: 'assets'
    })),
    importProvidersFrom(FormsModule)
  ]
};
