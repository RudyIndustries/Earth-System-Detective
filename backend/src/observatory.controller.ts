import { BadRequestException, Body, Controller, Get, Param, Post, Query, StreamableFile } from '@nestjs/common';
import { ObservatoryService } from './observatory.service';
import { MapService } from './map.service';

@Controller()
export class ObservatoryController {
  constructor(private readonly observatory: ObservatoryService, private readonly map: MapService) {}

  @Get('health')
  health() { return { status: 'ok' }; }

  @Get('dashboard')
  dashboard(@Query('method') method?: string) {
    return { ...this.observatory.dashboard(method), liveMap: this.map.configured };
  }

  @Get('bodies/:id')
  detail(@Param('id') id: string, @Query('method') method?: string) { return this.observatory.detail(id, method); }

  @Get('bodies/:id/audit')
  audit(@Param('id') id: string, @Query('method') method?: string) { return this.observatory.history(id, method); }

  @Post('bodies/:id/reviews')
  review(@Param('id') id: string, @Body() body: Record<string, unknown>, @Query('method') method?: string) {
    return this.observatory.review(id, body, method);
  }

  @Get('weekly')
  weekly() { return this.observatory.weekly(); }

  @Get('results.json')
  download(@Query('method') method?: string) {
    return new StreamableFile(this.observatory.download(method), {
      type: 'application/json', disposition: 'attachment; filename="uma_results.json"',
    });
  }

  @Get('images/:folder/:filename')
  image(@Param('folder') folder: string, @Param('filename') filename: string) {
    return new StreamableFile(this.observatory.image(folder, filename), { type: 'image/png' });
  }

  @Get('map/elevation')
  async elevation(@Query('body') body?: string) {
    const { results } = this.observatory.dashboard();
    const snapshot = body ? this.observatory.places(body).slice(0, 30) : results;
    return this.map.elevations(snapshot);
  }

  @Get('map/texture')
  async texture(@Query('mode') mode: string, @Query('year') input: string, @Query('fires') fires?: string) {
    const year = Number(input);
    if (!Number.isInteger(year) || year < 1985 || year > 2025 || (mode !== 'water' && mode !== 'landsat')) {
      throw new BadRequestException('Elige un modo de mapa y un año entre 1985 y 2025.');
    }
    return { url: await this.map.texture(mode, year, fires === 'true') };
  }
}
