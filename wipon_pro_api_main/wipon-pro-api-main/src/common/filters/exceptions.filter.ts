import { ArgumentsHost, Catch, ExceptionFilter, HttpException, HttpStatus } from '@nestjs/common';
import createCustomErrorLogger from '../logger/error-logger';
import { Request, Response } from 'express';

@Catch()
export class ExceptionsFilter implements ExceptionFilter {
  catch(exception: any, host: ArgumentsHost): any {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    const httpStatus = exception instanceof HttpException ? exception.getStatus() : HttpStatus.INTERNAL_SERVER_ERROR;
    const responseMessage =
      httpStatus === HttpStatus.INTERNAL_SERVER_ERROR ? 'Internal server error' : exception.response;
    const errorStack = exception.stack.replace(/[\n]/g, ' ');

    if (httpStatus > 499 || httpStatus < 400) {
      const errorLogger = createCustomErrorLogger();
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      const user = request?.user;
      errorLogger.log('error', {
        httpStatus,
        errorStack,
        responseMessage,
        url: request.url,
        body: request.body,
        userId: user ? user.id : null,
      });
    }

    response.status(httpStatus).json({
      statusCode: httpStatus,
      message: responseMessage.message ? responseMessage.message : responseMessage,
      error: exception.message,
    });
  }
}
