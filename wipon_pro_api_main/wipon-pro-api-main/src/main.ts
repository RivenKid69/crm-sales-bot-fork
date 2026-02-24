import { NestFactory } from '@nestjs/core';
import { AppModule } from 'src/app.module';
import { json, urlencoded } from 'express';
import { VersionInterceptor } from './common/interceptor/version.interceptor';
import { ExceptionsFilter } from './common/filters/exceptions.filter';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

async function bootstrap() {
  const PORT = process.env.SERVER_PORT || 3000;
  const app = await NestFactory.create(AppModule);

  const options = new DocumentBuilder()
    .setTitle('Wipon Pro')
    .setDescription('Wipon Pro API documentation')
    .setVersion('1.0')
    .build();
  const document = SwaggerModule.createDocument(app, options);
  SwaggerModule.setup('swagger', app, document);

  app.enableCors({
    origin: true,
  });
  app.setGlobalPrefix('v1');
  // app.useGlobalInterceptors(new TransformInterceptor());
  app.useGlobalInterceptors(new VersionInterceptor());
  app.useGlobalFilters(new ExceptionsFilter());
  app.use(json({ limit: '10mb' }));
  app.use(urlencoded({ extended: true, limit: '10mb' }));
  await app.listen(PORT);
}

bootstrap();
