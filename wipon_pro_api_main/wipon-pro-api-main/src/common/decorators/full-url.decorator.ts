import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { Request } from 'express';
import * as url from 'url';

const fullUrl = (req: Request) => {
  return url.format({
    protocol: req.protocol,
    host: req.get('host'),
    pathname: req.path,
  });
};

export const FullUrl = createParamDecorator((data: unknown, ctx: ExecutionContext) => {
  const request: Request = ctx.switchToHttp().getRequest();
  return fullUrl(request);
});
