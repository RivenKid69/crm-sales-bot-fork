import { IsIn, IsInt, IsOptional, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class GetUsersTransactionsDto {
  @IsOptional()
  @IsInt()
  @ApiProperty({
    type: Number,
    required: false,
  })
  page: number;

  @IsOptional()
  @IsString()
  @IsIn(['income', 'expense'])
  @ApiProperty({
    type: String,
    required: false,
    description: 'Filtering users transactions for income and expense',
  })
  type: string;
}
